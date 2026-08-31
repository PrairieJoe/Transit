"""End-to-end demand summary and scenario execution."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Database
from .demand import Journey, assign_journeys, summarize_od_demand
from .metrics import compare_counts, network_kpis
from .scenarios import apply_changes

def summarize_card_demand(database: Database, dataset_id: str) -> dict[str, int]:
    rows = database.query_all(
        "SELECT COALESCE(route_id, 'UNKNOWN'), COUNT(*) FROM card_transactions "
        "WHERE dataset_id = ? GROUP BY COALESCE(route_id, 'UNKNOWN')",
        (dataset_id,),
    )
    return {route_id: count for route_id, count in rows}


def summarize_stop_demand(database: Database, dataset_id: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    boarding_rows = database.query_all(
        "SELECT boarding_stop_id, COUNT(*) FROM card_transactions "
        "WHERE dataset_id = ? AND boarding_stop_id IS NOT NULL GROUP BY boarding_stop_id",
        (dataset_id,),
    )
    alighting_rows = database.query_all(
        "SELECT alighting_stop_id, COUNT(*) FROM card_transactions "
        "WHERE dataset_id = ? AND alighting_stop_id IS NOT NULL GROUP BY alighting_stop_id",
        (dataset_id,),
    )
    for stop_id, count in boarding_rows:
        result.setdefault(stop_id, {"boardings": 0, "alightings": 0})["boardings"] = count
    for stop_id, count in alighting_rows:
        result.setdefault(stop_id, {"boardings": 0, "alightings": 0})["alightings"] = count
    return dict(sorted(result.items()))

def run_scenario(
    database: Database,
    name: str,
    base_counts: dict[str, int | float],
    scenario_counts: dict[str, int | float],
    base_network: dict[str, Any] | None = None,
    changes: list[dict[str, Any]] | None = None,
    scenario_id: str | None = None,
) -> dict:
    scenario_id = scenario_id or f"scenario-{uuid.uuid4().hex[:12]}"
    changes = changes or []
    existing = database.query_one("SELECT id FROM scenarios WHERE id = ?", (scenario_id,))
    if existing:
        database.execute("UPDATE scenarios SET status = 'running' WHERE id = ?", (scenario_id,))
    else:
        database.execute(
            "INSERT INTO scenarios (id,name,base_network_version,status,created_at) VALUES (?,?,?,?,?)",
            (scenario_id, name, "base-v1", "running", datetime.now(timezone.utc).isoformat()),
        )
    try:
        scenario_network = apply_changes(base_network or {"routes": {}}, changes)
    except (KeyError, TypeError, ValueError):
        database.execute("UPDATE scenarios SET status = 'failed' WHERE id = ?", (scenario_id,))
        raise
    for change in changes:
        database.execute(
            "INSERT INTO scenario_changes (id,scenario_id,change_type,payload_json) VALUES (?,?,?,?)",
            (uuid.uuid4().hex, scenario_id, change["change_type"], json.dumps(change, ensure_ascii=False)),
        )
    metrics = compare_counts(base_counts, scenario_counts)
    for scope_id, values in metrics.items():
        database.execute(
            "INSERT INTO metric_results (id,scenario_id,scope_type,scope_id,metric_name,base_value,scenario_value,delta_value,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, scenario_id, "ROUTE", scope_id, "boardings",
             values["base_value"], values["scenario_value"], values["delta_value"],
             datetime.now(timezone.utc).isoformat()),
        )
    database.execute("UPDATE scenarios SET status = 'completed' WHERE id = ?", (scenario_id,))
    return {"scenario_id": scenario_id, "metrics": metrics, "scenario_network": scenario_network}


def run_network_scenario(
    database: Database,
    name: str,
    journeys: list[Journey | dict[str, Any]],
    base_network: dict[str, Any],
    changes: list[dict[str, Any]],
    beta: float = 0.08,
    scenario_id: str | None = None,
) -> dict:
    normalized = [item if isinstance(item, Journey) else Journey(
        id=str(item.get("id") or item.get("transaction_id")),
        origin_stop_id=str(item["boarding_stop_id"]),
        destination_stop_id=item.get("alighting_stop_id") or None,
        destination_status="OBSERVED" if item.get("alighting_stop_id") else "UNKNOWN",
    ) for item in journeys]
    try:
        scenario_network = apply_changes(base_network, changes)
    except (KeyError, TypeError, ValueError):
        failed_id = scenario_id or f"scenario-{uuid.uuid4().hex[:12]}"
        if database.query_one("SELECT id FROM scenarios WHERE id = ?", (failed_id,)):
            database.execute("UPDATE scenarios SET status = 'failed' WHERE id = ?", (failed_id,))
        else:
            database.execute(
                "INSERT INTO scenarios (id,name,base_network_version,status,created_at) VALUES (?,?,?,?,?)",
                (failed_id, name, "base-v1", "failed", datetime.now(timezone.utc).isoformat()),
            )
        raise
    base_counts = assign_journeys(normalized, base_network, beta=beta)
    scenario_counts = assign_journeys(normalized, scenario_network, beta=beta)
    result = run_scenario(database, name, base_counts, scenario_counts, base_network, changes, scenario_id=scenario_id)
    base_od = summarize_od_demand(normalized)
    scenario_od = base_od.copy()
    base_stops = _journey_stop_metrics(normalized)
    scenario_stops = base_stops.copy()
    base_network_kpis = network_kpis(base_network.get("routes", {}))
    scenario_network_kpis = network_kpis(scenario_network.get("routes", {}))
    _persist_scope_metrics(database, result["scenario_id"], "OD", "journeys", base_od, scenario_od)
    _persist_scope_metrics(database, result["scenario_id"], "STOP", "boardings", base_stops["boardings"], scenario_stops["boardings"])
    _persist_scope_metrics(database, result["scenario_id"], "STOP", "alightings", base_stops["alightings"], scenario_stops["alightings"])
    _persist_scope_metrics(database, result["scenario_id"], "NETWORK", "kpi", base_network_kpis, scenario_network_kpis)
    return {**result, "base_counts": base_counts, "scenario_counts": scenario_counts}


def _journey_stop_metrics(journeys: list[Journey]) -> dict[str, dict[str, float]]:
    boardings: dict[str, float] = {}
    alightings: dict[str, float] = {}
    for journey in journeys:
        boardings[journey.origin_stop_id] = boardings.get(journey.origin_stop_id, 0.0) + 1.0
        if journey.destination_stop_id and journey.destination_status in {"OBSERVED", "INFERRED"}:
            alightings[journey.destination_stop_id] = alightings.get(journey.destination_stop_id, 0.0) + 1.0
    return {"boardings": boardings, "alightings": alightings}


def _persist_scope_metrics(database: Database, scenario_id: str, scope_type: str, metric_name: str,
                           base: dict[str, int | float], scenario: dict[str, int | float]) -> None:
    for scope_id, values in compare_counts(base, scenario).items():
        database.execute(
            "INSERT INTO metric_results (id,scenario_id,scope_type,scope_id,metric_name,base_value,scenario_value,delta_value,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, scenario_id, scope_type, scope_id, metric_name,
             values["base_value"], values["scenario_value"], values["delta_value"],
             datetime.now(timezone.utc).isoformat()),
        )

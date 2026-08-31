"""End-to-end demand summary and scenario execution."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import Database
from .metrics import compare_counts
from .scenarios import apply_changes

def summarize_card_demand(database: Database, dataset_id: str) -> dict[str, int]:
    rows = database.query_all(
        "SELECT COALESCE(route_id, 'UNKNOWN'), COUNT(*) FROM card_transactions "
        "WHERE dataset_id = ? GROUP BY COALESCE(route_id, 'UNKNOWN')",
        (dataset_id,),
    )
    return {route_id: count for route_id, count in rows}

def run_scenario(
    database: Database,
    name: str,
    base_counts: dict[str, int | float],
    scenario_counts: dict[str, int | float],
    base_network: dict[str, Any] | None = None,
    changes: list[dict[str, Any]] | None = None,
) -> dict:
    scenario_id = f"scenario-{uuid.uuid4().hex[:12]}"
    changes = changes or []
    scenario_network = apply_changes(base_network or {"routes": {}}, changes)
    database.execute(
        "INSERT INTO scenarios (id,name,base_network_version,status,created_at) VALUES (?,?,?,?,?)",
        (scenario_id, name, "base-v1", "running", datetime.now(timezone.utc).isoformat()),
    )
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


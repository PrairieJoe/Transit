"""End-to-end demand summary and scenario execution."""
import json
import uuid
from datetime import datetime, timezone

from .db import Database
from .metrics import compare_counts


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
) -> dict:
    scenario_id = f"scenario-{uuid.uuid4().hex[:12]}"
    database.execute(
        "INSERT INTO scenarios (id,name,base_network_version,status,created_at) VALUES (?,?,?,?,?)",
        (scenario_id, name, "base-v1", "running", datetime.now(timezone.utc).isoformat()),
    )
    metrics = compare_counts(base_counts, scenario_counts)
    for scope_id, values in metrics.items():
        database.execute(
            "INSERT INTO metric_results "
            "(id,scenario_id,scope_type,scope_id,metric_name,base_value,scenario_value,delta_value,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, scenario_id, "ROUTE", scope_id, "boardings",
             values["base_value"], values["scenario_value"], values["delta_value"],
             datetime.now(timezone.utc).isoformat()),
        )
    database.execute("UPDATE scenarios SET status = 'completed' WHERE id = ?", (scenario_id,))
    return {"scenario_id": scenario_id, "metrics": metrics}


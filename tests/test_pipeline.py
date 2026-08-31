import csv
import json

from transit.db import Database
from transit.ingest import register_file
from transit.pipeline import summarize_card_demand, run_scenario


def test_summarize_card_demand_counts_routes(tmp_path):
    source = tmp_path / "cards.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["transaction_id", "transaction_time", "route_id", "boarding_stop_id"])
        writer.writeheader()
        writer.writerows([
            {"transaction_id": "T1", "transaction_time": "2026-08-31T08:00:00", "route_id": "R1", "boarding_stop_id": "S1"},
            {"transaction_id": "T2", "transaction_time": "2026-08-31T08:01:00", "route_id": "R1", "boarding_stop_id": "S1"},
            {"transaction_id": "T3", "transaction_time": "2026-08-31T08:02:00", "route_id": "R2", "boarding_stop_id": "S2"},
        ])
    database = Database(tmp_path / "db.sqlite3")
    dataset_id = register_file(database, source, "CARD")

    assert summarize_card_demand(database, dataset_id) == {"R1": 2, "R2": 1}


def test_run_scenario_persists_compare_metrics(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    result = run_scenario(database, "demo", {"R1": 10}, {"R1": 13, "R2": 2})

    assert result["scenario_id"]
    assert result["metrics"]["R1"]["delta_value"] == 3
    assert database.query_one("SELECT status FROM scenarios")[0] == "completed"

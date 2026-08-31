import csv
import json

from transit.db import Database
from transit.ingest import register_file
from transit.pipeline import run_network_scenario, run_scenario, summarize_card_demand, summarize_stop_demand


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


def test_summarize_stop_demand_counts_boardings_and_alightings(tmp_path):
    source = tmp_path / "cards.csv"
    source.write_text(
        "transaction_id,transaction_time,route_id,boarding_stop_id,alighting_stop_id\n"
        "T1,2026-08-31T08:00:00,R1,S1,S2\n"
        "T2,2026-08-31T08:01:00,R1,S1,S3\n", encoding="utf-8"
    )
    database = Database(tmp_path / "db.sqlite3")
    dataset_id = register_file(database, source, "CARD")

    assert summarize_stop_demand(database, dataset_id) == {
        "S1": {"boardings": 2, "alightings": 0},
        "S2": {"boardings": 0, "alightings": 1},
        "S3": {"boardings": 0, "alightings": 1},
    }


def test_run_scenario_persists_compare_metrics(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    result = run_scenario(database, "demo", {"R1": 10}, {"R1": 13, "R2": 2})

    assert result["scenario_id"]
    assert result["metrics"]["R1"]["delta_value"] == 3
    assert database.query_one("SELECT status FROM scenarios")[0] == "completed"


def test_run_scenario_applies_route_changes_and_returns_network(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    result = run_scenario(
        database,
        "route change",
        {"R1": 10},
        {"R1": 8, "R2": 2},
        base_network={"routes": {"R1": {"stops": ["S1", "S2"]}}},
        changes=[{"change_type": "CREATE_ROUTE", "route_id": "R2", "stops": ["S2", "S3"]}],
    )

    assert result["scenario_network"]["routes"]["R2"]["stops"] == ["S2", "S3"]
    assert database.query_one("SELECT COUNT(*) FROM scenario_changes")[0] == 1


def test_run_network_scenario_reassigns_journeys_after_route_change(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    journeys = [{"transaction_id": "T1", "boarding_stop_id": "S1", "alighting_stop_id": "S3"}]
    network = {"routes": {"R1": {"stops": ["S1", "S2", "S3"], "headway_seconds": 600}}}

    result = run_network_scenario(
        database, "network assignment", journeys, network,
        [{"change_type": "CREATE_ROUTE", "route_id": "R2", "stops": ["S1", "S3"], "headway_seconds": 600}],
    )

    assert result["base_counts"]["R1"] == 1.0
    assert result["scenario_counts"]["R2"] > 0


def test_run_scenario_records_failed_status_without_mutating_base(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    base_network = {"routes": {"R1": {"stops": ["S1", "S2"]}}}

    try:
        run_scenario(
            database, "invalid", {"R1": 1}, {"R1": 1}, base_network,
            [{"change_type": "ADD_STOP", "route_id": "missing", "stop_id": "S3"}],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid scenario should fail")

    assert database.query_one("SELECT status FROM scenarios WHERE name = 'invalid'")[0] == "failed"
    assert base_network == {"routes": {"R1": {"stops": ["S1", "S2"]}}}

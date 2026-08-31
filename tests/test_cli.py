import csv
import json

from transit.cli import main
from transit.db import Database
from transit.ingest import register_file
from transit.pipeline import run_scenario


def test_cli_register_prints_dataset_id(tmp_path, capsys):
    source = tmp_path / "cards.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["transaction_id", "transaction_time", "boarding_stop_id"])
        writer.writeheader()
        writer.writerow({"transaction_id": "T1", "transaction_time": "2026-08-31T08:00:00", "boarding_stop_id": "S1"})

    assert main(["--db", str(tmp_path / "transit.sqlite3"), "dataset", "register", "--file", str(source), "--type", "card"]) == 0
    assert "dataset_id=" in capsys.readouterr().out


def test_cli_demand_summarize_prints_route_counts(tmp_path, capsys):
    source = tmp_path / "cards.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["transaction_id", "transaction_time", "route_id", "boarding_stop_id"])
        writer.writeheader()
        writer.writerow({"transaction_id": "T1", "transaction_time": "2026-08-31T08:00:00", "route_id": "R1", "boarding_stop_id": "S1"})
    db_path = tmp_path / "transit.sqlite3"
    dataset_id = register_file(Database(db_path), source, "CARD")

    assert main(["--db", str(db_path), "demand", "summarize", "--dataset", dataset_id]) == 0
    assert '"R1": 1' in capsys.readouterr().out


def test_cli_scenario_run_prints_metrics(tmp_path, capsys):
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text('{"name":"new route","base_counts":{"R1":10},"scenario_counts":{"R1":13}}', encoding="utf-8")

    assert main(["--db", str(tmp_path / "db.sqlite3"), "scenario", "run", "--file", str(scenario_file)]) == 0
    assert '"delta_value": 3' in capsys.readouterr().out


def test_cli_scenario_compare_prints_persisted_metrics(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite3"
    scenario_id = run_scenario(Database(db_path), "compare me", {"R1": 10}, {"R1": 13})["scenario_id"]

    assert main(["--db", str(db_path), "scenario", "compare", "--scenario", scenario_id]) == 0
    assert '"delta_value": 3' in capsys.readouterr().out


def test_cli_scenario_compare_exports_csv(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite3"
    scenario_id = run_scenario(Database(db_path), "export me", {"R1": 10}, {"R1": 13})["scenario_id"]
    output = tmp_path / "metrics.csv"

    assert main(["--db", str(db_path), "scenario", "compare", "--scenario", scenario_id, "--format", "csv", "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8").splitlines() == ["scope_id,base_value,scenario_value,delta_value", "R1,10,13,3"]
    assert f"output={output}" in capsys.readouterr().out


def test_cli_scenario_run_applies_network_changes(tmp_path, capsys):
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps({
        "name": "network change",
        "base_counts": {"R1": 10},
        "scenario_counts": {"R1": 8, "R2": 2},
        "base_network": {"routes": {"R1": {"stops": ["S1", "S2"]}}},
        "changes": [{"change_type": "CREATE_ROUTE", "route_id": "R2", "stops": ["S2", "S3"]}],
    }), encoding="utf-8")

    assert main(["--db", str(tmp_path / "db.sqlite3"), "scenario", "run", "--file", str(scenario_file)]) == 0
    assert '"R2": {"stops": ["S2", "S3"]}' in capsys.readouterr().out


def test_cli_scenario_compare_exports_geojson_from_network(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite3"
    scenario_id = run_scenario(Database(db_path), "geo", {"R1": 1}, {"R1": 1})["scenario_id"]
    network = tmp_path / "network.json"
    network.write_text(json.dumps({"routes": {"R1": {"coordinates": [[127.0, 37.0], [127.1, 37.1]]}}}), encoding="utf-8")
    output = tmp_path / "routes.geojson"

    assert main(["--db", str(db_path), "scenario", "compare", "--scenario", scenario_id, "--format", "geojson", "--network", str(network), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["type"] == "FeatureCollection"
    assert f"output={output}" in capsys.readouterr().out

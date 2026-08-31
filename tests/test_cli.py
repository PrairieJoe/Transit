import csv

from transit.cli import main
from transit.db import Database
from transit.ingest import register_file


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

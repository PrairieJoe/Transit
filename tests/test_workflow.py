import csv
import json
import sqlite3

from transit.db import Database
from transit.ingest import register_file
from transit.metrics import compare_counts, export_geojson, export_metrics_csv


def test_register_card_csv_persists_dataset_and_transactions(tmp_path):
    path = tmp_path / "cards.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["transaction_id", "transaction_time", "boarding_stop_id", "alighting_stop_id"],
        )
        writer.writeheader()
        writer.writerow({
            "transaction_id": "T1",
            "transaction_time": "2026-08-31T08:00:00",
            "boarding_stop_id": "S1",
            "alighting_stop_id": "S2",
        })

    database = Database(tmp_path / "transit.sqlite3")
    dataset_id = register_file(database, path, source_type="CARD")

    assert database.query_one("SELECT COUNT(*) FROM datasets")[0] == 1
    assert database.query_one("SELECT COUNT(*) FROM card_transactions")[0] == 1
    assert dataset_id


def test_compare_counts_returns_base_scenario_and_delta():
    result = compare_counts({"R1": 10}, {"R1": 13, "R2": 2})

    assert result["R1"] == {"base_value": 10, "scenario_value": 13, "delta_value": 3}
    assert result["R2"]["delta_value"] == 2


def test_export_geojson_writes_feature_collection(tmp_path):
    output = tmp_path / "routes.geojson"
    export_geojson(output, [{"id": "R1", "coordinates": [[127.0, 37.0], [127.1, 37.1]]}])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["geometry"]["type"] == "LineString"


def test_export_metrics_csv_writes_stable_metric_columns(tmp_path):
    output = tmp_path / "metrics.csv"
    export_metrics_csv(output, {"R1": {"base_value": 10, "scenario_value": 13, "delta_value": 3}})

    assert output.read_text(encoding="utf-8").splitlines() == [
        "scope_id,base_value,scenario_value,delta_value",
        "R1,10,13,3",
    ]

from transit.api.app import create_app
from transit.db import Database
from transit.pipeline import run_scenario


def test_api_exposes_health_and_scenario_metrics(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    scenario_id = run_scenario(database, "api", {"R1": 10}, {"R1": 13})["scenario_id"]
    app = create_app(database)

    health = next(route.endpoint for route in app.routes if route.path == "/health")()
    metrics = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}/metrics")(scenario_id)

    assert health == {"status": "ok"}
    assert metrics["R1"]["delta_value"] == 3


def test_api_exposes_stop_demand_scope(tmp_path):
    database = Database(tmp_path / "api.sqlite3")
    dataset_id = "card-demo"
    database.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)", (dataset_id, "cards", "CARD", "cards.csv", "hash", "1.0", "passed", "now"))
    database.execute("INSERT INTO card_transactions VALUES (?,?,?,?,?,?,?,?,?,?)", ("t1", dataset_id, "now", None, "R1", "S1", "S2", None, "BOARDING", "OBSERVED"))
    database.execute("INSERT INTO card_transactions VALUES (?,?,?,?,?,?,?,?,?,?)", ("t2", dataset_id, "now", None, "R1", "S1", None, None, "BOARDING", "UNKNOWN"))
    app = create_app(database)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/demand")
    assert endpoint(dataset_id, "stop") == {"S1": {"boardings": 2, "alightings": 0}, "S2": {"boardings": 0, "alightings": 1}}


def test_api_exposes_detailed_scenario_metrics(tmp_path):
    database = Database(tmp_path / "api.sqlite3")
    result = run_scenario(database, "api", {"R1": 10}, {"R1": 13})
    app = create_app(database)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}/metrics/detail")
    details = endpoint(result["scenario_id"])
    assert details[0]["scope_type"] == "ROUTE"

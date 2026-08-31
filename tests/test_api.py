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

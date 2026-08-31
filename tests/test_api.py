from transit.api.app import create_app
from transit.db import Database
from transit.pipeline import run_scenario
from transit.regional import register_regional_archive
from fastapi.testclient import TestClient


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


def test_api_lists_regional_datasets_and_routes(tmp_path):
    database_path = tmp_path / "regional-api.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    app = create_app(Database(database_path))

    datasets = next(route.endpoint for route in app.routes if route.path == "/datasets")()
    routes = next(route.endpoint for route in app.routes if route.path == "/networks/{network_version}/routes")(registered["dataset_id"])

    assert datasets[0]["id"] == registered["dataset_id"]
    assert len(routes) > 0
    assert {"id", "name", "stops"} <= routes[0].keys()


def test_api_creates_and_reads_scenario_draft(tmp_path):
    database = Database(tmp_path / "scenario-api.sqlite3")
    app = create_app(database)
    create = next(route.endpoint for route in app.routes if route.path == "/scenarios")
    read = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}" and "GET" in route.methods)
    status = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}/status")

    created = create({
        "name": "정류장 조정",
        "base_network_version": "base-v1",
        "changes": [{"change_type": "REMOVE_STOP", "route_id": "R1", "stop_id": "S2"}],
    })

    assert created["status"] == "draft"
    assert read(created["id"])["changes"][0]["change_type"] == "REMOVE_STOP"
    assert status(created["id"])["status"] == "pending"


def test_api_updates_scenario_draft(tmp_path):
    database = Database(tmp_path / "scenario-patch.sqlite3")
    app = create_app(database)
    create = next(route.endpoint for route in app.routes if route.path == "/scenarios" and "POST" in route.methods)
    update = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}" and "PATCH" in route.methods)
    read = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}" and "GET" in route.methods)
    created = create({"name": "초안", "base_network_version": "base-v1", "changes": []})

    updated = update(created["id"], {"name": "수정 초안", "changes": [{"change_type": "CHANGE_HEADWAY", "route_id": "R1", "headway_s": 600}]})

    assert updated["status"] == "draft"
    assert read(created["id"])["name"] == "수정 초안"
    assert read(created["id"])["changes"][0]["change_type"] == "CHANGE_HEADWAY"


def test_api_returns_network_geojson_and_mapping(tmp_path):
    database_path = tmp_path / "geo.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    database = Database(database_path)
    app = create_app(database)
    mapping = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/mapping" and "POST" in route.methods)
    geojson = next(route.endpoint for route in app.routes if route.path == "/networks/{network_version}/geojson")

    saved = mapping(registered["dataset_id"], {"confirmed": True, "mappings": [{"source_column": "route_id", "canonical_field": "route_id"}]})
    result = geojson(registered["dataset_id"])

    assert saved["mapping_status"] == "pending"
    assert result["type"] == "FeatureCollection"
    assert result["features"]
    assert {feature["geometry"]["type"] for feature in result["features"]} == {"LineString", "Point"}


def test_api_runs_regional_route_adjustment_without_mutating_base(tmp_path):
    database_path = tmp_path / "e2e.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    database = Database(database_path)
    app = create_app(database)
    create = next(route.endpoint for route in app.routes if route.path == "/scenarios")
    run = next(route.endpoint for route in app.routes if route.path == "/scenarios/{scenario_id}/run")
    mapping = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/mapping" and "POST" in route.methods)
    suggestions = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/mapping" and "GET" in route.methods)(registered["dataset_id"])["suggestions"]
    mapping(registered["dataset_id"], {"confirmed": True, "mappings": suggestions})
    routes_before = database.query_one("SELECT COUNT(*) FROM route_stops")[0]
    scenario = create({"name": "regional e2e", "base_network_version": registered["dataset_id"], "changes": [{"change_type": "REMOVE_STOP", "route_id": "46001001", "stop_id": "4600433"}]})

    result = run(scenario["id"])

    assert result["status"] == "completed"
    assert result["metrics"]
    assert any(values["base_value"] > 0 for values in result["metrics"].values())
    assert database.query_one("SELECT COUNT(*) FROM route_stops")[0] == routes_before
    assert database.query_one("SELECT status FROM scenarios WHERE id = ?", (scenario["id"],))[0] == "completed"
    run_snapshot = database.query_one("SELECT status,base_snapshot,result_snapshot FROM scenario_runs WHERE scenario_id = ? ORDER BY started_at DESC LIMIT 1", (scenario["id"],))
    assert run_snapshot[0] == "completed"
    assert run_snapshot[1] and run_snapshot[2]
    run(scenario["id"])
    repeated_snapshot = database.query_one("SELECT result_snapshot FROM scenario_runs WHERE scenario_id = ? ORDER BY started_at DESC LIMIT 1", (scenario["id"],))[0]
    assert repeated_snapshot == run_snapshot[2]


def test_api_accepts_daily_zip_upload(tmp_path):
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    client = TestClient(create_app(Database(tmp_path / "upload.sqlite3")))

    response = client.post("/datasets/uploads/daily", files={"file": (archive.name, archive.read_bytes(), "application/zip")})

    assert response.status_code == 200
    assert response.json()["service_date"] == "20240420"


def test_api_http_request_can_use_database_from_fastapi_threadpool(tmp_path):
    database = Database(tmp_path / "threaded.sqlite3")
    database.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)", ("ds1", "sample", "DAILY", "sample.zip", "hash-thread", "1.0", "passed", "now"))
    client = TestClient(create_app(database))

    response = client.get("/datasets")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "ds1"


def test_api_exposes_mapping_suggestions_for_regional_dataset(tmp_path):
    database_path = tmp_path / "mapping.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    app = create_app(Database(database_path))
    mapping = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/mapping" and "GET" in route.methods)

    result = mapping(registered["dataset_id"])

    assert result["dataset_id"] == registered["dataset_id"]
    assert any(item["canonical_field"] == "route_id" for item in result["suggestions"])


def test_dataset_detail_requires_complete_mapping_before_confirming(tmp_path):
    database_path = tmp_path / "mapping-status.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    app = create_app(Database(database_path))
    save = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}/mapping" and "POST" in route.methods)
    detail = next(route.endpoint for route in app.routes if route.path == "/datasets/{dataset_id}")

    save(registered["dataset_id"], {"confirmed": True, "mappings": [{"source_file_type": "ROUTE", "source_column": "3", "canonical_field": "route_id"}]})

    assert detail(registered["dataset_id"])["mapping_status"] == "pending"


def test_api_blocks_scenario_run_until_mapping_is_confirmed(tmp_path):
    database_path = tmp_path / "blocked.sqlite3"
    archive = __import__("pathlib").Path(__file__).parents[1] / "data/sample/daily/DATA_20240420.zip"
    registered = register_regional_archive(database_path, archive, "DAILY")
    client = TestClient(create_app(Database(database_path)))

    scenario = client.post("/scenarios", json={"name": "Pending mapping", "base_network_version": registered["dataset_id"], "changes": []}).json()
    response = client.post(f"/scenarios/{scenario['id']}/run")

    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "dataset.not_ready"


def test_api_persists_failed_run_when_network_cannot_be_built(tmp_path):
    database = Database(tmp_path / "failed-run.sqlite3")
    client = TestClient(create_app(database))
    scenario = client.post("/scenarios", json={"name": "Missing network", "base_network_version": "missing", "changes": []}).json()

    response = client.post(f"/scenarios/{scenario['id']}/run")

    assert response.status_code == 422
    assert database.query_one("SELECT status,error_code FROM scenario_runs WHERE scenario_id = ?", (scenario["id"],)) == ("failed", "scenario.run_failed")

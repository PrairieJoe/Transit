"""FastAPI API for data registration, map browsing, and scenarios."""
import json
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ..db import Database
from ..network import build_network
from ..pipeline import run_network_scenario
from ..regional import RegionalArchiveError, register_regional_archive

def create_app(database: Database | None = None) -> FastAPI:
    app = FastAPI(title="Transit API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    db = database

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/datasets")
    def datasets() -> list[dict]:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        return [
            {"id": row[0], "name": row[1], "source_type": row[2], "quality_status": row[3], "created_at": row[4]}
            for row in db.query_all("SELECT id,name,source_type,quality_status,created_at FROM datasets ORDER BY created_at DESC")
        ]

    def _upload_archive(upload: UploadFile, source_type: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        if not upload.filename or not upload.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=422, detail={"error_code": "archive.invalid", "message": "a ZIP file is required"})
        upload_dir = db.path.parent / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / f"{uuid.uuid4().hex}-{Path(upload.filename).name}"
        with destination.open("wb") as stream:
            shutil.copyfileobj(upload.file, stream)
        try:
            return register_regional_archive(db.path, destination, source_type)
        except RegionalArchiveError as error:
            raise HTTPException(status_code=422, detail={"error_code": "archive.invalid", "message": str(error)}) from error

    @app.post("/datasets/uploads/common")
    def upload_common(file: UploadFile = File(...)) -> dict:
        return _upload_archive(file, "COMMON")

    @app.post("/datasets/uploads/daily")
    def upload_daily(file: UploadFile = File(...)) -> dict:
        return _upload_archive(file, "DAILY")

    @app.get("/datasets/{dataset_id}")
    def dataset_detail(dataset_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        row = db.query_one("SELECT id,name,source_type,quality_status,created_at FROM datasets WHERE id = ?", (dataset_id,))
        if not row:
            raise HTTPException(status_code=404, detail="dataset not found")
        files = db.query_all("SELECT archive_name,member_name,file_type,file_hash,service_date FROM dataset_files WHERE dataset_id = ? ORDER BY member_name", (dataset_id,))
        confirmed = db.query_one("SELECT COUNT(*) FROM dataset_mappings WHERE dataset_id = ? AND confirmed = 1", (dataset_id,))[0]
        return {"id": row[0], "name": row[1], "source_type": row[2], "quality_status": row[3], "mapping_status": "confirmed" if confirmed else "pending", "created_at": row[4], "files": [dict(zip(("archive_name", "member_name", "file_type", "file_hash", "service_date"), item)) for item in files]}

    @app.get("/datasets/{dataset_id}/validation")
    def dataset_validation(dataset_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        row = db.query_one("SELECT quality_status FROM datasets WHERE id = ?", (dataset_id,))
        if not row:
            raise HTTPException(status_code=404, detail="dataset not found")
        errors = db.query_all("SELECT error_code,field,message FROM validation_errors WHERE dataset_id = ?", (dataset_id,))
        return {"dataset_id": dataset_id, "quality_status": row[0], "errors": [dict(zip(("error_code", "field", "message"), item)) for item in errors]}

    @app.post("/datasets/{dataset_id}/mapping")
    def save_mapping(dataset_id: str, payload: dict) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        if not db.query_one("SELECT id FROM datasets WHERE id = ?", (dataset_id,)):
            raise HTTPException(status_code=404, detail="dataset not found")
        for mapping in payload.get("mappings", []):
            db.execute("INSERT OR REPLACE INTO dataset_mappings (dataset_id,source_file_type,source_column,canonical_field,confidence,confirmed) VALUES (?,?,?,?,?,?)", (dataset_id, mapping.get("source_file_type", "UNKNOWN"), mapping["source_column"], mapping["canonical_field"], float(mapping.get("confidence", 1.0)), int(bool(payload.get("confirmed")))))
        return {"dataset_id": dataset_id, "mapping_status": "confirmed" if payload.get("confirmed") else "pending"}

    @app.get("/datasets/{dataset_id}/mapping")
    def get_mapping(dataset_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        if not db.query_one("SELECT id FROM datasets WHERE id = ?", (dataset_id,)):
            raise HTTPException(status_code=404, detail="dataset not found")
        saved = db.query_all("SELECT source_file_type,source_column,canonical_field,confidence,confirmed FROM dataset_mappings WHERE dataset_id = ? ORDER BY source_file_type,source_column", (dataset_id,))
        suggestions = [
            {"source_file_type": "ROUTE", "source_column": "3", "canonical_field": "route_id", "confidence": 0.95},
            {"source_file_type": "ROUTE", "source_column": "4", "canonical_field": "route_name", "confidence": 0.95},
            {"source_file_type": "ROUTESTTN", "source_column": "7", "canonical_field": "stop_id", "confidence": 0.98},
            {"source_file_type": "ROUTESTTN", "source_column": "9", "canonical_field": "latitude", "confidence": 0.99},
            {"source_file_type": "ROUTESTTN", "source_column": "10", "canonical_field": "longitude", "confidence": 0.99},
            {"source_file_type": "DWTCD", "source_column": "9", "canonical_field": "transaction_time", "confidence": 0.9},
            {"source_file_type": "DWTCD", "source_column": "11", "canonical_field": "route_id", "confidence": 0.8},
            {"source_file_type": "DWTCD", "source_column": "13", "canonical_field": "boarding_stop_id", "confidence": 0.8},
        ]
        return {"dataset_id": dataset_id, "saved": [dict(zip(("source_file_type", "source_column", "canonical_field", "confidence", "confirmed"), row)) for row in saved], "suggestions": suggestions}

    @app.get("/networks/{network_version}/routes")
    def network_routes(network_version: str) -> list[dict]:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        try:
            network = build_network(db, network_version)
        except ValueError:
            raise HTTPException(status_code=404, detail="network not found")
        return [{"id": route_id, "name": route["name"], "direction": route.get("direction"), "stops": route["stops"], "coordinates": route["coordinates"]} for route_id, route in network["routes"].items()]

    @app.get("/networks/{network_version}/geojson")
    def network_geojson(network_version: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        try:
            network = build_network(db, network_version)
        except ValueError:
            raise HTTPException(status_code=404, detail="network not found")
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": route["coordinates"]}, "properties": {"route_id": route_id, "name": route["name"], "direction": route.get("direction"), "stops": route["stops"]}} for route_id, route in network["routes"].items()]}

    @app.get("/routes/{route_id}")
    def route_detail(route_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        row = db.query_one("SELECT id,source_route_id,name,direction,source_dataset_id FROM routes WHERE id = ? OR source_route_id = ?", (route_id, route_id))
        if not row:
            raise HTTPException(status_code=404, detail="route not found")
        stops = db.query_all("SELECT s.source_stop_id,s.name,s.latitude,s.longitude,rs.stop_sequence FROM route_stops rs JOIN stops s ON s.id=rs.stop_id WHERE rs.route_id=? ORDER BY rs.stop_sequence", (row[0],))
        return {"id": row[1], "name": row[2], "direction": row[3], "dataset_id": row[4], "stops": [{"id": item[0], "name": item[1], "latitude": item[2], "longitude": item[3], "sequence": item[4]} for item in stops]}

    @app.get("/routes/{route_id}/stops")
    def route_stops(route_id: str) -> list[dict]:
        return route_detail(route_id)["stops"]

    @app.get("/datasets/{dataset_id}/demand")
    def dataset_demand(dataset_id: str, scope: str = "route") -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        if scope not in {"route", "stop"}:
            raise HTTPException(status_code=422, detail="scope must be route or stop")
        if scope == "stop":
            rows = db.query_all(
                "SELECT stop_id, SUM(boardings), SUM(alightings) FROM ("
                "SELECT boarding_stop_id AS stop_id, COUNT(*) AS boardings, 0 AS alightings "
                "FROM card_transactions WHERE dataset_id = ? AND boarding_stop_id IS NOT NULL GROUP BY boarding_stop_id "
                "UNION ALL "
                "SELECT alighting_stop_id AS stop_id, 0 AS boardings, COUNT(*) AS alightings "
                "FROM card_transactions WHERE dataset_id = ? AND alighting_stop_id IS NOT NULL GROUP BY alighting_stop_id"
                ") GROUP BY stop_id ORDER BY stop_id",
                (dataset_id, dataset_id),
            )
            if not rows:
                raise HTTPException(status_code=404, detail="dataset demand not found")
            return {stop_id: {"boardings": boardings, "alightings": alightings} for stop_id, boardings, alightings in rows}
        rows = db.query_all(
            "SELECT COALESCE(route_id, 'UNKNOWN'), COUNT(*) FROM card_transactions "
            "WHERE dataset_id = ? GROUP BY COALESCE(route_id, 'UNKNOWN')",
            (dataset_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="dataset demand not found")
        return {route_id: count for route_id, count in rows}

    @app.get("/scenarios/{scenario_id}/metrics")
    def scenario_metrics(scenario_id: str) -> dict[str, dict[str, float]]:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        rows = db.query_all(
            "SELECT scope_id, base_value, scenario_value, delta_value "
            "FROM metric_results WHERE scenario_id = ? AND scope_type = 'ROUTE' AND metric_name = 'boardings' ORDER BY scope_id",
            (scenario_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="scenario metrics not found")
        return {
            scope_id: {"base_value": base, "scenario_value": scenario, "delta_value": delta}
            for scope_id, base, scenario, delta in rows
        }

    @app.get("/scenarios/{scenario_id}/metrics/detail")
    def scenario_metric_details(scenario_id: str) -> list[dict]:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        rows = db.query_all(
            "SELECT scope_type, scope_id, metric_name, base_value, scenario_value, delta_value "
            "FROM metric_results WHERE scenario_id = ? ORDER BY scope_type, scope_id, metric_name",
            (scenario_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="scenario metrics not found")
        return [
            {"scope_type": scope_type, "scope_id": scope_id, "metric_name": metric_name,
             "base_value": base, "scenario_value": scenario, "delta_value": delta}
            for scope_type, scope_id, metric_name, base, scenario, delta in rows
        ]

    @app.post("/scenarios")
    def create_scenario(payload: dict) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        scenario_id = f"scenario-{uuid.uuid4().hex[:12]}"
        changes = payload.get("changes", [])
        database_version = payload.get("base_network_version", "base-v1")
        db.execute("INSERT INTO scenarios (id,name,base_network_version,status,created_at) VALUES (?,?,?,?,datetime('now'))", (scenario_id, payload.get("name", "Untitled scenario"), database_version, "draft"))
        db.execute("INSERT INTO scenario_inputs (scenario_id,payload_json) VALUES (?,?)", (scenario_id, json.dumps(payload, ensure_ascii=False)))
        for change in changes:
            db.execute("INSERT INTO scenario_changes (id,scenario_id,change_type,payload_json) VALUES (?,?,?,?)", (uuid.uuid4().hex, scenario_id, change["change_type"], json.dumps(change, ensure_ascii=False)))
        return {"id": scenario_id, "name": payload.get("name", "Untitled scenario"), "base_network_version": database_version, "status": "draft", "changes": changes}

    @app.get("/scenarios")
    def scenarios() -> list[dict]:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        return [{"id": row[0], "name": row[1], "base_network_version": row[2], "status": row[3], "created_at": row[4]} for row in db.query_all("SELECT id,name,base_network_version,status,created_at FROM scenarios ORDER BY created_at DESC")]

    @app.patch("/scenarios/{scenario_id}")
    def update_scenario(scenario_id: str, payload: dict) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        current = db.query_one("SELECT id,name,base_network_version,status FROM scenarios WHERE id = ?", (scenario_id,))
        if not current:
            raise HTTPException(status_code=404, detail="scenario not found")
        if current[3] != "draft":
            raise HTTPException(status_code=409, detail={"error_code": "scenario.not_editable", "message": "only draft scenarios can be edited", "scenario_id": scenario_id})
        name = payload.get("name", current[1])
        changes = payload.get("changes", [])
        db.execute("UPDATE scenarios SET name = ? WHERE id = ?", (name, scenario_id))
        db.execute("DELETE FROM scenario_changes WHERE scenario_id = ?", (scenario_id,))
        for change in changes:
            db.execute("INSERT INTO scenario_changes (id,scenario_id,change_type,payload_json) VALUES (?,?,?,?)", (uuid.uuid4().hex, scenario_id, change["change_type"], json.dumps(change, ensure_ascii=False)))
        db.execute("UPDATE scenario_inputs SET payload_json = ? WHERE scenario_id = ?", (json.dumps({**payload, "name": name, "base_network_version": current[2], "changes": changes}, ensure_ascii=False), scenario_id))
        return {"id": scenario_id, "name": name, "base_network_version": current[2], "status": "draft", "changes": changes}

    @app.get("/scenarios/{scenario_id}")
    def scenario_detail(scenario_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        row = db.query_one("SELECT id,name,base_network_version,status,created_at FROM scenarios WHERE id = ?", (scenario_id,))
        if not row:
            raise HTTPException(status_code=404, detail="scenario not found")
        changes = db.query_all("SELECT payload_json FROM scenario_changes WHERE scenario_id = ? ORDER BY rowid", (scenario_id,))
        return {"id": row[0], "name": row[1], "base_network_version": row[2], "status": row[3], "created_at": row[4], "changes": [json.loads(item[0]) for item in changes]}

    @app.get("/scenarios/{scenario_id}/status")
    def scenario_status(scenario_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        row = db.query_one("SELECT status FROM scenarios WHERE id = ?", (scenario_id,))
        if not row:
            raise HTTPException(status_code=404, detail="scenario not found")
        run = db.query_one("SELECT status FROM scenario_runs WHERE scenario_id = ? ORDER BY started_at DESC LIMIT 1", (scenario_id,))
        return {"scenario_id": scenario_id, "status": run[0] if run else ("pending" if row[0] == "draft" else row[0])}

    @app.post("/scenarios/{scenario_id}/run")
    def run_saved_scenario(scenario_id: str) -> dict:
        if db is None:
            raise HTTPException(status_code=503, detail="database is not configured")
        scenario = db.query_one("SELECT name,base_network_version,status FROM scenarios WHERE id = ?", (scenario_id,))
        if not scenario:
            raise HTTPException(status_code=404, detail="scenario not found")
        quality = db.query_one("SELECT quality_status FROM datasets WHERE id = ?", (scenario[1],))
        if quality and quality[0] != "passed":
            raise HTTPException(status_code=422, detail={"error_code": "dataset.not_ready", "message": "dataset quality validation must pass before analysis", "scenario_id": scenario_id})
        if quality and not db.query_one("SELECT 1 FROM dataset_mappings WHERE dataset_id = ? AND confirmed = 1 LIMIT 1", (scenario[1],)):
            raise HTTPException(status_code=422, detail={"error_code": "dataset.not_ready", "message": "dataset mapping must be confirmed before analysis", "scenario_id": scenario_id})
        payload = db.query_one("SELECT payload_json FROM scenario_inputs WHERE scenario_id = ?", (scenario_id,))
        changes = json.loads(payload[0]).get("changes", []) if payload else []
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO scenario_runs (id,scenario_id,status,base_snapshot,started_at) VALUES (?,?,?,?,?)", (run_id, scenario_id, "running", "pending", started_at))
        try:
            network = build_network(db, scenario[1])
            base_snapshot = hashlib.sha256(json.dumps(network, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            db.execute("UPDATE scenario_runs SET base_snapshot = ? WHERE id = ?", (base_snapshot, run_id))
            journeys = [{"id": row[0], "boarding_stop_id": row[1], "alighting_stop_id": row[2]} for row in db.query_all("SELECT id,boarding_stop_id,alighting_stop_id FROM card_transactions WHERE dataset_id = ?", (scenario[1],))]
            result = run_network_scenario(db, scenario[0], journeys, network, changes, scenario_id=scenario_id)
            result_snapshot = hashlib.sha256(json.dumps({"network": result["scenario_network"], "metrics": result["metrics"]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            db.execute("UPDATE scenario_runs SET status = 'completed', result_snapshot = ?, completed_at = ? WHERE id = ?", (result_snapshot, datetime.now(timezone.utc).isoformat(), run_id))
            return {"scenario_id": scenario_id, "status": "completed", "metrics": result["metrics"]}
        except (KeyError, TypeError, ValueError) as error:
            db.execute("UPDATE scenarios SET status = 'failed' WHERE id = ?", (scenario_id,))
            if db.query_one("SELECT id FROM scenario_runs WHERE id = ?", (run_id,)):
                db.execute("UPDATE scenario_runs SET status = 'failed', error_code = ?, error_message = ?, completed_at = ? WHERE id = ?", ("scenario.run_failed", str(error), datetime.now(timezone.utc).isoformat(), run_id))
            raise HTTPException(status_code=422, detail={"error_code": "scenario.run_failed", "message": str(error), "scenario_id": scenario_id}) from error

    return app

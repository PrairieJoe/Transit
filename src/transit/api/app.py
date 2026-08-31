"""FastAPI read API for the Transit MVP."""
from fastapi import FastAPI, HTTPException

from ..db import Database

def create_app(database: Database | None = None) -> FastAPI:
    app = FastAPI(title="Transit API", version="0.1.0")
    db = database

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    return app

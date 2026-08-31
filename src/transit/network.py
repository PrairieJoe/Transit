"""Canonical network construction from BIS rows persisted in SQLite."""
from typing import Any

from .db import Database


def build_network(database: Database, dataset_id: str) -> dict[str, Any]:
    """Build a deterministic route/stop network snapshot for a BIS dataset."""
    rows = database.query_all(
        "SELECT r.source_route_id, r.name, r.direction, rs.stop_id, rs.stop_sequence, "
        "s.source_stop_id, s.name, s.latitude, s.longitude "
        "FROM route_stops rs "
        "JOIN routes r ON r.id = rs.route_id "
        "JOIN stops s ON s.id = rs.stop_id "
        "WHERE r.source_dataset_id = ? ORDER BY r.source_route_id, rs.stop_sequence",
        (dataset_id,),
    )
    if not rows:
        raise ValueError(f"BIS network not found for dataset: {dataset_id}")
    routes: dict[str, dict[str, Any]] = {}
    for route_id, name, direction, stop_id, sequence, source_stop_id, stop_name, latitude, longitude in rows:
        route = routes.setdefault(route_id, {"name": name, "direction": direction, "stops": [], "coordinates": []})
        route["stops"].append(source_stop_id)
        route["coordinates"].append([longitude, latitude])
    return {"dataset_id": dataset_id, "routes": routes}

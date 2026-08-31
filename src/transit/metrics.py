"""Scenario metrics and export."""
import csv
import json
from math import ceil
from pathlib import Path
from typing import Iterable

def required_vehicles(round_trip_time_seconds: int | float, headway_seconds: int | float) -> int:
    if round_trip_time_seconds < 0 or headway_seconds <= 0:
        raise ValueError("round_trip_time_seconds must be non-negative and headway_seconds positive")
    return ceil(round_trip_time_seconds / headway_seconds)

def operating_metrics(routes: dict[str, dict]) -> dict[str, dict[str, int | float]]:
    result = {}
    for route_id, route in routes.items():
        headway = route.get("headway_seconds")
        round_trip = route.get("round_trip_time_seconds")
        if headway is None or round_trip is None:
            continue
        start_hour, start_minute = (int(value) for value in route.get("service_start_time", "06:00").split(":", 1))
        end_hour, end_minute = (int(value) for value in route.get("service_end_time", "23:00").split(":", 1))
        service_seconds = (end_hour * 3600 + end_minute * 60) - (start_hour * 3600 + start_minute * 60)
        if service_seconds < 0:
            raise ValueError("service_end_time must not be earlier than service_start_time")
        result[route_id] = {
            "service_trips": service_seconds // headway + 1,
            "required_vehicles": required_vehicles(round_trip, headway),
            "headway_seconds": headway,
            "round_trip_time_seconds": round_trip,
        }
    return result


def network_kpis(routes: dict[str, dict]) -> dict[str, int | float]:
    """Return deterministic network-level coverage and operating KPIs."""
    operating = operating_metrics(routes)
    return {
        "route_count": len(routes),
        "stop_coverage": len({stop for route in routes.values() for stop in route.get("stops", [])}),
        "service_trips": sum(item["service_trips"] for item in operating.values()),
        "required_vehicles": sum(item["required_vehicles"] for item in operating.values()),
    }

def compare_counts(base: dict[str, int | float], scenario: dict[str, int | float]) -> dict[str, dict[str, int | float]]:
    return {key: {"base_value": base.get(key, 0), "scenario_value": scenario.get(key, 0), "delta_value": scenario.get(key, 0) - base.get(key, 0)} for key in sorted(set(base) | set(scenario))}

def export_metrics_csv(path: str | Path, metrics: dict[str, dict[str, int | float]]) -> None:
    def csv_value(value: int | float) -> int | float:
        return int(value) if isinstance(value, float) and value.is_integer() else value

    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["scope_id", "base_value", "scenario_value", "delta_value"])
        writer.writeheader()
        for scope_id in sorted(metrics):
            writer.writerow({"scope_id": scope_id, **{key: csv_value(value) for key, value in metrics[scope_id].items()}})

def export_geojson(path: str | Path, features: Iterable[dict]) -> None:
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": item["id"]}, "geometry": {"type": "LineString", "coordinates": item["coordinates"]}} for item in features]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

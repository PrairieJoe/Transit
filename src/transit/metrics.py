"""Scenario metrics and export."""
import json
from math import ceil
from pathlib import Path
from typing import Iterable

def required_vehicles(round_trip_time_seconds: int | float, headway_seconds: int | float) -> int:
    if round_trip_time_seconds < 0 or headway_seconds <= 0:
        raise ValueError("round_trip_time_seconds must be non-negative and headway_seconds positive")
    return ceil(round_trip_time_seconds / headway_seconds)

def compare_counts(base: dict[str, int | float], scenario: dict[str, int | float]) -> dict[str, dict[str, int | float]]:
    return {key: {"base_value": base.get(key, 0), "scenario_value": scenario.get(key, 0), "delta_value": scenario.get(key, 0) - base.get(key, 0)} for key in sorted(set(base) | set(scenario))}

def export_geojson(path: str | Path, features: Iterable[dict]) -> None:
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": item["id"]}, "geometry": {"type": "LineString", "coordinates": item["coordinates"]}} for item in features]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


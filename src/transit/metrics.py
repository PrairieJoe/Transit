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

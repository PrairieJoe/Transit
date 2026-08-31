"""Demand and basic route-choice calculations."""
from dataclasses import dataclass
from math import exp
from typing import Any, Iterable


@dataclass(frozen=True)
class Journey:
    id: str
    origin_stop_id: str
    destination_stop_id: str | None
    destination_status: str


def build_journeys(rows: Iterable[dict[str, Any]]) -> list[Journey]:
    journeys: list[Journey] = []
    for index, row in enumerate(rows, start=1):
        destination = row.get("alighting_stop_id") or None
        journeys.append(Journey(
            id=str(row.get("transaction_id") or f"J{index}"),
            origin_stop_id=str(row.get("boarding_stop_id") or ""),
            destination_stop_id=destination,
            destination_status="OBSERVED" if destination else "UNKNOWN",
        ))
    return journeys


def assign_logit(costs: dict[str, float], beta: float = 0.08) -> dict[str, float]:
    if not costs:
        return {}
    utilities = {key: exp(-beta * value) for key, value in costs.items()}
    total = sum(utilities.values())
    return {key: value / total for key, value in utilities.items()}


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
        status = row.get("destination_status") or row.get("alighting_status")
        if status not in {"OBSERVED", "INFERRED", "UNKNOWN"}:
            status = "OBSERVED" if destination else "UNKNOWN"
        journeys.append(Journey(
            id=str(row.get("transaction_id") or f"J{index}"),
            origin_stop_id=str(row.get("boarding_stop_id") or ""),
            destination_stop_id=destination,
            destination_status=status,
        ))
    return journeys


def summarize_od_demand(journeys: Iterable[Journey]) -> dict[str, float]:
    """Count observed or otherwise known origin-destination journeys."""
    result: dict[str, float] = {}
    for journey in journeys:
        if not journey.destination_stop_id or journey.destination_status not in {"OBSERVED", "INFERRED"}:
            continue
        key = f"{journey.origin_stop_id}->{journey.destination_stop_id}"
        result[key] = result.get(key, 0.0) + 1.0
    return dict(sorted(result.items()))


def assign_logit(costs: dict[str, float], beta: float = 0.08) -> dict[str, float]:
    if not costs:
        return {}
    utilities = {key: exp(-beta * value) for key, value in costs.items()}
    total = sum(utilities.values())
    return {key: value / total for key, value in utilities.items()}


def assign_journeys(journeys: Iterable[Journey], network: dict[str, Any], beta: float = 0.08) -> dict[str, float]:
    """Return expected route shares for journeys with known destinations.

    The MVP uses stop-order compatibility and a deterministic proxy travel cost.
    OTP/OSRM can replace this function behind a future router adapter.
    """
    totals: dict[str, float] = {}
    od_counts: dict[tuple[str, str], int] = {}
    for journey in journeys:
        if journey.destination_stop_id is not None:
            key = (journey.origin_stop_id, journey.destination_stop_id)
            od_counts[key] = od_counts.get(key, 0) + 1
    routes = network.get("routes", {})
    routes_by_stop: dict[str, set[str]] = {}
    for route_id, route in routes.items():
        for stop_id in route.get("stops", []):
            routes_by_stop.setdefault(stop_id, set()).add(route_id)
    choice_cache: dict[tuple[str, str], dict[str, float]] = {}
    for (origin_stop_id, destination_stop_id), count in od_counts.items():
        cache_key = (origin_stop_id, destination_stop_id)
        shares = choice_cache.get(cache_key)
        if shares is None:
            costs: dict[str, float] = {}
            candidate_routes = routes_by_stop.get(origin_stop_id, set()) & routes_by_stop.get(destination_stop_id, set())
            for route_id in candidate_routes:
                route = routes[route_id]
                stops = route.get("stops", [])
                if origin_stop_id not in stops or destination_stop_id not in stops:
                    continue
                origin_index = stops.index(origin_stop_id)
                destination_index = stops.index(destination_stop_id)
                if destination_index <= origin_index:
                    continue
                segment_count = destination_index - origin_index
                speed_mps = float(route.get("speed_mps", 20_000 / 3_600))
                travel_time = segment_count * 300 / speed_mps
                waiting_time = float(route.get("headway_seconds", 600)) / 2
                costs[route_id] = travel_time + waiting_time
            shares = assign_logit(costs, beta=beta)
            choice_cache[cache_key] = shares
        for route_id, probability in shares.items():
            totals[route_id] = totals.get(route_id, 0.0) + probability * count
    return totals

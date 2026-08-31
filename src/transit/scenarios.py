"""Immutable bus scenario transformations."""
from copy import deepcopy
from typing import Any


SUPPORTED_CHANGES = {
    "CREATE_ROUTE",
    "DELETE_ROUTE",
    "ADD_STOP",
    "REMOVE_STOP",
    "REORDER_STOP",
    "CHANGE_HEADWAY",
    "CHANGE_SERVICE_WINDOW",
}


def apply_changes(base_network: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    scenario = deepcopy(base_network)
    scenario.setdefault("routes", {})
    for change in changes:
        change_type = change["change_type"]
        if change_type not in SUPPORTED_CHANGES:
            raise ValueError(f"unsupported change type: {change_type}")
        route_id = change.get("route_id")
        if change_type == "CREATE_ROUTE":
            if not route_id or route_id in scenario["routes"]:
                raise ValueError("route_id is required and must be new")
            scenario["routes"][route_id] = {
                key: value for key, value in change.items()
                if key not in {"change_type", "route_id"}
            }
        elif change_type == "DELETE_ROUTE":
            scenario["routes"].pop(route_id, None)
        elif route_id not in scenario["routes"]:
            raise ValueError(f"route does not exist: {route_id}")
        elif change_type == "ADD_STOP":
            scenario["routes"][route_id].setdefault("stops", []).append(change["stop_id"])
        elif change_type == "REMOVE_STOP":
            stops = scenario["routes"][route_id].setdefault("stops", [])
            scenario["routes"][route_id]["stops"] = [s for s in stops if s != change["stop_id"]]
        elif change_type == "REORDER_STOP":
            scenario["routes"][route_id]["stops"] = list(change["stops"])
        elif change_type == "CHANGE_HEADWAY":
            scenario["routes"][route_id]["headway_seconds"] = change["headway_seconds"]
        elif change_type == "CHANGE_SERVICE_WINDOW":
            scenario["routes"][route_id].update({
                key: change[key] for key in ("service_start_time", "service_end_time") if key in change
            })
    return scenario


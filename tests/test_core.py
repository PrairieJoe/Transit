import json

import pytest

from transit.demand import assign_journeys, assign_logit, build_journeys
from transit.ingest import validate_rows
from transit.metrics import required_vehicles
from transit.scenarios import apply_changes


def test_validate_rows_rejects_invalid_coordinates():
    rows = [{"stop_id": "S1", "latitude": 95, "longitude": 127}]

    report = validate_rows(rows, required_fields={"stop_id", "latitude", "longitude"})

    assert report.valid is False
    assert "latitude.out_of_range" in {error.code for error in report.errors}


def test_validate_rows_rejects_duplicate_identifiers_and_sequences():
    rows = [
        {"stop_id": "S1", "stop_sequence": "1"},
        {"stop_id": "S1", "stop_sequence": "1"},
    ]

    report = validate_rows(rows, required_fields={"stop_id", "stop_sequence"}, unique_fields={"stop_id"}, sequence_field="stop_sequence")

    assert report.valid is False
    codes = {error.code for error in report.errors}
    assert "stop_id.duplicate" in codes
    assert "stop_sequence.duplicate" in codes


def test_build_journeys_keeps_unknown_alighting_without_inventing_destination():
    rows = [
        {
            "transaction_id": "T1",
            "transaction_time": "2026-08-31T08:00:00",
            "boarding_stop_id": "S1",
            "alighting_stop_id": "",
        }
    ]

    journeys = build_journeys(rows)

    assert journeys[0].destination_stop_id is None
    assert journeys[0].destination_status == "UNKNOWN"


def test_assign_logit_probabilities_sum_to_one_and_favor_lower_cost():
    result = assign_logit({"R1": 10.0, "R2": 20.0}, beta=0.1)

    assert sum(result.values()) == pytest.approx(1.0)
    assert result["R1"] > result["R2"]


def test_apply_changes_creates_route_without_mutating_base_network():
    base = {"routes": {"R1": {"stops": ["S1", "S2"], "headway_seconds": 900}}}
    change = {
        "change_type": "CREATE_ROUTE",
        "route_id": "R2",
        "route_name": "신규노선",
        "stops": ["S2", "S3"],
        "headway_seconds": 600,
    }

    scenario = apply_changes(base, [change])

    assert "R2" not in base["routes"]
    assert scenario["routes"]["R2"]["stops"] == ["S2", "S3"]


def test_required_vehicles_rounds_up():
    assert required_vehicles(round_trip_time_seconds=3700, headway_seconds=600) == 7


def test_assign_journeys_allocates_existing_demand_to_matching_routes():
    journeys = build_journeys([
        {"transaction_id": "T1", "boarding_stop_id": "S1", "alighting_stop_id": "S3"},
    ])
    network = {
        "routes": {
            "R1": {"stops": ["S1", "S2", "S3"], "headway_seconds": 600},
            "R2": {"stops": ["S1", "S4", "S3"], "headway_seconds": 1200},
        }
    }

    result = assign_journeys(journeys, network)

    assert result["R1"] > result["R2"]
    assert sum(result.values()) == pytest.approx(1.0)

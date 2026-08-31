"""Input reading and validation primitives."""
import csv
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .db import Database

@dataclass(frozen=True)
class ValidationError:
    code: str
    field: str
    message: str

@dataclass
class ValidationReport:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

def validate_rows(
    rows: Iterable[dict[str, Any]],
    required_fields: set[str],
    unique_fields: set[str] | None = None,
    sequence_field: str | None = None,
) -> ValidationReport:
    errors = []
    seen: dict[str, set[Any]] = {field: set() for field in (unique_fields or set())}
    seen_sequences: set[Any] = set()
    for row_number, row in enumerate(rows, start=1):
        for required in sorted(required_fields):
            if required not in row or row[required] in (None, ""):
                errors.append(ValidationError(f"{required}.missing", required, f"row {row_number}: required field is missing"))
        for coordinate in ("latitude", "longitude"):
            value = row.get(coordinate)
            if value in (None, ""):
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                errors.append(ValidationError(f"{coordinate}.invalid", coordinate, f"row {row_number}: coordinate is not numeric"))
                continue
            limits = (-90, 90) if coordinate == "latitude" else (-180, 180)
            if not limits[0] <= numeric <= limits[1]:
                errors.append(ValidationError(f"{coordinate}.out_of_range", coordinate, f"row {row_number}: coordinate out of range"))
        for field in seen:
            value = row.get(field)
            if value in seen[field]:
                errors.append(ValidationError(f"{field}.duplicate", field, f"row {row_number}: duplicate value"))
            elif value not in (None, ""):
                seen[field].add(value)
        if sequence_field:
            value = row.get(sequence_field)
            if value not in (None, ""):
                try:
                    sequence = int(value)
                except (TypeError, ValueError):
                    sequence = None
                if sequence is not None and sequence in seen_sequences:
                    errors.append(ValidationError(f"{sequence_field}.duplicate", sequence_field, f"row {row_number}: duplicate sequence"))
                elif sequence is not None:
                    seen_sequences.add(sequence)
    return ValidationReport(valid=not errors, errors=errors)


def validate_bis_rows(rows: list[dict[str, Any]]) -> ValidationReport:
    """Validate BIS rows with stop sequence uniqueness scoped to each route."""
    required = {"route_id", "route_name", "stop_id", "stop_name", "stop_sequence", "latitude", "longitude"}
    errors = list(validate_rows(rows, required).errors)
    seen_route_stops: set[tuple[Any, Any]] = set()
    sequences_by_route: dict[Any, set[int]] = {}
    for row_number, row in enumerate(rows, start=1):
        route_id = row.get("route_id")
        stop_id = row.get("stop_id")
        if route_id not in (None, "") and stop_id not in (None, ""):
            pair = (route_id, stop_id)
            if pair in seen_route_stops:
                errors.append(ValidationError("route_stop.duplicate", "route_id,stop_id", f"row {row_number}: duplicate stop on route"))
            seen_route_stops.add(pair)
        if route_id in (None, ""):
            continue
        try:
            sequence = int(row.get("stop_sequence"))
        except (TypeError, ValueError):
            continue
        if sequence <= 0:
            errors.append(ValidationError("stop_sequence.invalid", "stop_sequence", f"row {row_number}: sequence must be positive"))
        seen = sequences_by_route.setdefault(route_id, set())
        if sequence in seen:
            errors.append(ValidationError("stop_sequence.duplicate", "stop_sequence", f"row {row_number}: duplicate sequence on route"))
        seen.add(sequence)
    return ValidationReport(valid=not errors, errors=errors)


def validate_time_fields(rows: list[dict[str, Any]], fields: set[str]) -> ValidationReport:
    errors: list[ValidationError] = []
    for row_number, row in enumerate(rows, start=1):
        for field in fields:
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                if field.endswith("_time"):
                    datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                else:
                    datetime.strptime(str(value), "%H:%M")
            except ValueError:
                errors.append(ValidationError(f"{field}.invalid", field, f"row {row_number}: invalid time value"))
    return ValidationReport(valid=not errors, errors=errors)

def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))

def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    if path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as parquet
        except ImportError as error:
            raise ValueError("Parquet input requires the optional pyarrow package") from error
        return parquet.read_table(path).to_pylist()
    raise ValueError("input must be a CSV or Parquet file")

def register_file(database: Database, path: str | Path, source_type: str) -> str:
    source_path = Path(path)
    source_type = source_type.upper()
    if source_type not in {"CARD", "BIS"}:
        raise ValueError("source_type must be CARD or BIS")
    rows = _read_rows(source_path)
    required = {"transaction_id", "transaction_time", "boarding_stop_id"} if source_type == "CARD" else {"route_id", "route_name", "stop_id", "stop_name", "stop_sequence", "latitude", "longitude"}
    report = validate_rows(rows, required, unique_fields={"transaction_id"}) if source_type == "CARD" else validate_bis_rows(rows)
    time_report = validate_time_fields(rows, {"transaction_time"} if source_type == "CARD" else {"service_start_time", "service_end_time"})
    report = ValidationReport(valid=report.valid and time_report.valid, errors=[*report.errors, *time_report.errors])
    file_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    existing = database.query_one("SELECT id FROM datasets WHERE file_hash = ?", (file_hash,))
    if existing:
        return existing[0]
    dataset_id = f"{source_type.lower()}-{file_hash[:12]}"
    database.execute(
        "INSERT INTO datasets (id,name,source_type,file_path,file_hash,schema_version,quality_status,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (dataset_id, source_path.name, source_type, str(source_path), file_hash, "1.0", "passed" if report.valid else "failed", datetime.now(timezone.utc).isoformat()),
    )
    for error in report.errors:
        database.execute(
            "INSERT INTO validation_errors (id,dataset_id,error_code,field,message) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, dataset_id, error.code, error.field, error.message),
        )
    if not report.valid:
        return dataset_id
    if source_type == "CARD":
        for row in rows:
            database.execute(
                "INSERT INTO card_transactions (id,dataset_id,transaction_time,journey_key,route_id,boarding_stop_id,alighting_stop_id,transfer_group_id,transaction_type,alighting_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["transaction_id"], dataset_id, row["transaction_time"], row.get("journey_key"), row.get("route_id"), row["boarding_stop_id"], row.get("alighting_stop_id"), row.get("transfer_id"), row.get("transaction_type", "BOARDING"), "OBSERVED" if row.get("alighting_stop_id") else "UNKNOWN"),
            )
    else:
        for row in rows:
            route_key = f"{dataset_id}:{row['route_id']}"
            stop_key = f"{dataset_id}:{row['stop_id']}"
            database.execute(
                "INSERT OR IGNORE INTO routes (id,source_dataset_id,source_route_id,name,direction,canonical_status) VALUES (?,?,?,?,?,?)",
                (route_key, dataset_id, row["route_id"], row["route_name"], row.get("direction"), "exact"),
            )
            database.execute(
                "INSERT OR IGNORE INTO stops (id,source_dataset_id,source_stop_id,name,latitude,longitude,canonical_status) VALUES (?,?,?,?,?,?,?)",
                (stop_key, dataset_id, row["stop_id"], row["stop_name"], float(row["latitude"]), float(row["longitude"]), "exact"),
            )
            database.execute(
                "INSERT INTO route_stops (route_id,stop_id,stop_sequence,distance_m,travel_time_s,source_type) VALUES (?,?,?,?,?,?)",
                (route_key, stop_key, int(row["stop_sequence"]), None, None, "BIS"),
            )
    return dataset_id

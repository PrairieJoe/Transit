"""Adapter for the regional ZIP/DAT sample format."""

from __future__ import annotations

import hashlib
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import Database


class RegionalArchiveError(ValueError):
    """Raised when a regional archive cannot be registered safely."""


MEMBER_TYPES = ("DWTCD", "ROUTESTTN", "ROUTE", "STTN")
SERVICE_DATE_RE = re.compile(r"(?:DATA_|ROUTE_|ROUTESTTN_|STTN_|DWTCD_)(\d{8})")


def classify_member(member_name: str) -> str | None:
    """Return the canonical type for a supported archive member."""
    stem = Path(member_name).name.upper()
    if stem.startswith("CD_") and stem.endswith(".DAT"):
        return "COMMON_CODE"
    if stem.startswith("COLUMNDEFINITION") and stem.endswith(".XLSX"):
        return "COLUMN_DEFINITION"
    for member_type in MEMBER_TYPES:
        if stem.startswith(member_type + "_") and stem.endswith(".DAT"):
            return member_type
    return None


def parse_pipe_dat(content: str, encoding: str = "utf-8") -> list[list[str]]:
    """Parse a pipe-delimited DAT payload without dropping empty fields."""
    if not content:
        return []
    return [line.rstrip("\r\n").split("|") for line in content.splitlines()]


def _decode(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RegionalArchiveError("archive member is not UTF-8, CP949, or EUC-KR")


def _service_date(archive_path: Path, member_names: list[str]) -> str | None:
    for candidate in [archive_path.name, *member_names]:
        match = SERVICE_DATE_RE.search(candidate.upper())
        if match:
            return match.group(1)
    return None


def inspect_archive(archive_path: str | Path) -> dict[str, Any]:
    """Inspect supported members and return parsed regional metadata."""
    path = Path(archive_path)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise RegionalArchiveError("archive_path must point to a ZIP file")
    with zipfile.ZipFile(path) as archive:
        members = []
        for info in archive.infolist():
            file_type = classify_member(info.filename)
            if file_type is None:
                continue
            payload = archive.read(info)
            row_count = None if file_type == "COLUMN_DEFINITION" else len(parse_pipe_dat(_decode(payload)))
            members.append({
                "member_name": info.filename,
                "file_type": file_type,
                "file_hash": hashlib.sha256(payload).hexdigest(),
                "row_count": row_count,
            })
    if not members:
        raise RegionalArchiveError("archive contains no supported regional DAT members")
    return {"service_date": _service_date(path, [m["member_name"] for m in members]), "members": members}


def _member_rows(archive: zipfile.ZipFile, member_name: str) -> list[list[str]]:
    return parse_pipe_dat(_decode(archive.read(member_name)))


def _transaction_rows(rows: list[list[str]], dataset_id: str) -> list[tuple[str, ...]]:
    """Map the observed regional DWTCD positions into the canonical card table."""
    result = []
    for index, row in enumerate(rows):
        if len(row) < 15 or not row[9]:
            continue
        source_key = f"{row[3]}|{row[9]}|{row[13]}|{index}"
        transaction_id = hashlib.sha256(source_key.encode()).hexdigest()[:32]
        journey_key = hashlib.sha256(row[3].encode()).hexdigest()[:32] if row[3] else None
        alighting_stop = row[17] if len(row) > 17 and row[17] else None
        result.append((transaction_id, dataset_id, row[9], journey_key, row[11] or None, row[13] or None, alighting_stop, row[21] or None if len(row) > 21 else None, "BOARDING", "OBSERVED" if alighting_stop else "UNKNOWN"))
    return result


def register_regional_archive(
    database_path: str | Path,
    archive_path: str | Path,
    source_type: str,
) -> dict[str, Any]:
    """Register one COMMONCD or daily regional archive in SQLite."""
    source_type = source_type.upper()
    if source_type not in {"COMMON", "DAILY"}:
        raise RegionalArchiveError("source_type must be COMMON or DAILY")
    path = Path(archive_path)
    inspection = inspect_archive(path)
    archive_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    database = Database(database_path)
    try:
        existing = database.query_one("SELECT id FROM datasets WHERE file_hash = ?", (archive_hash,))
        if existing:
            return {**inspection, "dataset_id": existing[0], "quality_status": "passed", "reused": True}
        dataset_id = f"{source_type.lower()}-{archive_hash[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        database.execute(
            "INSERT INTO datasets (id,name,source_type,file_path,file_hash,schema_version,quality_status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (dataset_id, path.name, source_type, str(path), archive_hash, "regional-1.0", "passed", now),
        )
        with zipfile.ZipFile(path) as archive:
            for member in inspection["members"]:
                database.execute(
                    "INSERT INTO dataset_files (id,dataset_id,archive_name,member_name,file_type,file_hash,service_date,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, dataset_id, path.name, member["member_name"], member["file_type"], member["file_hash"], inspection["service_date"], now),
                )
            if source_type == "DAILY":
                route_member = next((m for m in inspection["members"] if m["file_type"] == "ROUTESTTN"), None)
                transaction_member = next((m for m in inspection["members"] if m["file_type"] == "DWTCD"), None)
                if transaction_member:
                    transactions = _transaction_rows(_member_rows(archive, transaction_member["member_name"]), dataset_id)
                    database.connection.executemany("INSERT OR IGNORE INTO card_transactions (id,dataset_id,transaction_time,journey_key,route_id,boarding_stop_id,alighting_stop_id,transfer_group_id,transaction_type,alighting_status) VALUES (?,?,?,?,?,?,?,?,?,?)", transactions)
                if route_member:
                    route_rows = []
                    stop_rows = []
                    route_stop_rows = []
                    for row in _member_rows(archive, route_member["member_name"]):
                        if len(row) < 11:
                            continue
                        route_id, route_name, stop_sequence, stop_id = row[3], row[4], row[6], row[7]
                        try:
                            latitude, longitude, sequence = float(row[9]), float(row[10]), int(stop_sequence)
                        except (ValueError, TypeError):
                            continue
                        route_key = f"{dataset_id}:{route_id}"
                        stop_key = f"{dataset_id}:{stop_id}"
                        distance = float(row[13]) if len(row) > 13 and row[13] else None
                        route_rows.append((route_key, dataset_id, route_id, route_name, row[5] or None, "exact"))
                        stop_rows.append((stop_key, dataset_id, stop_id, row[8], latitude, longitude, "exact"))
                        route_stop_rows.append((route_key, stop_key, sequence, distance, None, "REGIONAL"))
                    database.connection.executemany("INSERT OR IGNORE INTO routes (id,source_dataset_id,source_route_id,name,direction,canonical_status) VALUES (?,?,?,?,?,?)", route_rows)
                    database.connection.executemany("INSERT OR IGNORE INTO stops (id,source_dataset_id,source_stop_id,name,latitude,longitude,canonical_status) VALUES (?,?,?,?,?,?,?)", stop_rows)
                    database.connection.executemany("INSERT OR IGNORE INTO route_stops (route_id,stop_id,stop_sequence,distance_m,travel_time_s,source_type) VALUES (?,?,?,?,?,?)", route_stop_rows)
                    database.connection.commit()
        return {**inspection, "dataset_id": dataset_id, "quality_status": "passed", "reused": False}
    finally:
        database.close()

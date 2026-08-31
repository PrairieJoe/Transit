from pathlib import Path

import pytest

from transit.regional import (
    RegionalArchiveError,
    classify_member,
    parse_pipe_dat,
    register_regional_archive,
)


ROOT = Path(__file__).parents[1]


def test_classify_regional_members_from_daily_archive():
    assert classify_member("ROUTE_20240420.dat") == "ROUTE"
    assert classify_member("ROUTESTTN_20240420.dat") == "ROUTESTTN"
    assert classify_member("STTN_20240420.dat") == "STTN"
    assert classify_member("DWTCD_20240420.dat") == "DWTCD"
    assert classify_member("notes.txt") is None


def test_classify_common_code_members_and_register_common_archive(tmp_path):
    assert classify_member("CD_CARDGB.dat") == "COMMON_CODE"
    assert classify_member("ColumnDefinition_20250320.xlsx") == "COLUMN_DEFINITION"
    result = register_regional_archive(tmp_path / "common.sqlite3", ROOT / "data/sample/common/COMMONCD.zip", "COMMON")
    assert result["quality_status"] == "passed"
    assert {member["file_type"] for member in result["members"]} == {"COMMON_CODE", "COLUMN_DEFINITION"}


def test_parse_pipe_dat_preserves_korean_and_empty_fields():
    rows = parse_pipe_dat("A|정류장||34.7|127.6\n", encoding="utf-8")
    assert rows == [["A", "정류장", "", "34.7", "127.6"]]


def test_register_regional_archive_indexes_members_and_service_date(tmp_path):
    database_path = tmp_path / "regional.sqlite3"
    archive = ROOT / "data/sample/daily/DATA_20240420.zip"

    result = register_regional_archive(database_path, archive, source_type="DAILY")

    assert result["service_date"] == "20240420"
    assert {member["file_type"] for member in result["members"]} == {"DWTCD", "ROUTE", "ROUTESTTN", "STTN"}
    assert result["quality_status"] == "passed"


def test_register_regional_archive_rejects_unknown_source_type(tmp_path):
    with pytest.raises(RegionalArchiveError, match="source_type"):
        register_regional_archive(tmp_path / "db.sqlite3", ROOT / "data/sample/daily/DATA_20240420.zip", "CARD")

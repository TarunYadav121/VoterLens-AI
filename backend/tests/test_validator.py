"""
test_validator.py — VoterLens AI
=================================
Automated tests for validator.py covering all 15 scenarios (TV-01 to TV-15).
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as cfg
import validator


def test_tv01_valid_csv_with_all_columns(valid_previous_csv_bytes):
    """TV-01: Valid CSV with all required columns -> No errors, no blocking."""
    result, df = validator.validate_and_load(valid_previous_csv_bytes, "previous_file")
    assert not result.has_blocking_errors
    assert len(result.errors) == 0
    assert df is not None
    assert len(df) == 4


def test_tv02_empty_csv_header_only():
    """TV-02: Empty CSV (header only or 0 rows) -> ERROR: empty file."""
    csv_bytes = b"record_id,name,area_id,area_name\n"
    result, df = validator.validate_and_load(csv_bytes, "previous_file")
    assert result.has_blocking_errors
    assert any(e.type == "EMPTY_FILE" for e in result.errors)
    assert df is None


def test_tv03_unreadable_file_content():
    """TV-03: Corrupt or binary content -> ERROR: unreadable."""
    corrupt_bytes = b"\x00\xff\xfe\x12\x34\x56"
    result, df = validator.validate_and_load(corrupt_bytes, "previous_file")
    assert result.has_blocking_errors
    assert len(result.errors) > 0


def test_tv04_missing_record_id_column():
    """TV-04: Missing record_id column -> ERROR: missing required column."""
    csv_bytes = b"name,area_id,area_name\nArjun,A01,North Valley\n"
    result, df = validator.validate_and_load(csv_bytes, "previous_file")
    assert result.has_blocking_errors
    assert any(e.type == "MISSING_REQUIRED_COLUMN" and e.column == "record_id" for e in result.errors)
    assert df is None


def test_tv05_missing_area_id_column():
    """TV-05: Missing area_id column -> ERROR: missing required column."""
    csv_bytes = b"record_id,name,area_name\nSYN-001,Arjun,North Valley\n"
    result, df = validator.validate_and_load(csv_bytes, "previous_file")
    assert result.has_blocking_errors
    assert any(e.type == "MISSING_REQUIRED_COLUMN" and e.column == "area_id" for e in result.errors)
    assert df is None


def test_tv06_null_record_id():
    """TV-06: Row with null record_id -> ERROR (row-level): missing identifier."""
    csv_bytes = b"record_id,name,area_id,area_name\n,Arjun,A01,North Valley\nSYN-002,Priya,A01,North Valley\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(e.type == "MISSING_RECORD_ID" for e in result.errors)
    assert 0 in result.ambiguous_row_indices


def test_tv07_duplicate_record_id():
    """TV-07: Two rows with same record_id -> ERROR (row-level): duplicate identifier."""
    csv_bytes = b"record_id,name,area_id,area_name\nSYN-001,Arjun,A01,North Valley\nSYN-001,Arjun Clone,A01,North Valley\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(e.type == "DUPLICATE_RECORD_ID" for e in result.errors)
    assert 0 in result.ambiguous_row_indices
    assert 1 in result.ambiguous_row_indices


def test_tv08_non_numeric_age():
    """TV-08: Non-numeric age value ('thirty') -> ERROR (row-level): invalid age."""
    csv_bytes = b"record_id,name,area_id,area_name,age\nSYN-001,Arjun,A01,North Valley,thirty\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(e.type == "INVALID_AGE_TYPE" for e in result.errors)


def test_tv09_missing_age():
    """TV-09: Missing age (null) -> WARNING: missing age."""
    csv_bytes = b"record_id,name,area_id,area_name,age\nSYN-001,Arjun,A01,North Valley,\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(w.type == "MISSING_AGE" for w in result.warnings)


def test_tv10_age_below_plausible_min():
    """TV-10: Age 14 (below 17) -> REVIEW_FLAG: age below plausible minimum."""
    csv_bytes = b"record_id,name,area_id,area_name,age\nSYN-001,Arjun,A01,North Valley,14\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(rf.type == "AGE_OUT_OF_RANGE" for rf in result.review_flags)


def test_tv11_age_above_plausible_max():
    """TV-11: Age 130 (above 120) -> REVIEW_FLAG: age above plausible maximum."""
    csv_bytes = b"record_id,name,area_id,area_name,age\nSYN-001,Arjun,A01,North Valley,130\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(rf.type == "AGE_OUT_OF_RANGE" for rf in result.review_flags)


def test_tv12_file_too_large():
    """TV-12: File size exceeds limit -> ERROR: file too large."""
    dummy_large = b"a" * (cfg.MAX_FILE_SIZE_BYTES + 10)
    result = validator.validate_csv(dummy_large, "previous_file")
    assert result.has_blocking_errors
    assert any(e.type == "FILE_TOO_LARGE" for e in result.errors)


def test_tv13_unsupported_file_extension():
    """TV-13: File with .xlsx extension -> ERROR: unsupported file type."""
    csv_bytes = b"record_id,name,area_id,area_name\nSYN-001,Arjun,A01,North Valley\n"
    result = validator.validate_csv(csv_bytes, "previous_file", filename="voters.xlsx")
    assert result.has_blocking_errors
    assert any(e.type == "UNSUPPORTED_EXTENSION" for e in result.errors)


def test_tv14_optional_column_absent():
    """TV-14: Optional column 'gender' absent -> WARNING: missing optional column."""
    csv_bytes = b"record_id,name,area_id,area_name\nSYN-001,Arjun,A01,North Valley\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert not result.has_blocking_errors
    assert any(w.type == "MISSING_OPTIONAL_COLUMN" and w.column == "gender" for w in result.warnings)


def test_tv15_invalid_gender_value():
    """TV-15: Invalid gender value ('X') -> REVIEW_FLAG: invalid gender."""
    csv_bytes = b"record_id,name,area_id,area_name,gender\nSYN-001,Arjun,A01,North Valley,X\n"
    result = validator.validate_csv(csv_bytes, "previous_file")
    assert any(rf.type == "INVALID_GENDER" for rf in result.review_flags)

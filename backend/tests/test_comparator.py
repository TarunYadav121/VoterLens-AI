"""
test_comparator.py — VoterLens AI
==================================
Automated tests for comparator.py covering all 12 scenarios (TC-01 to TC-12).
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import pytest

import comparator


def test_tc01_identical_dataframes(valid_previous_df):
    """TC-01: Identical DataFrames -> All UNCHANGED; 0 added, 0 deleted."""
    res = comparator.compare(valid_previous_df, valid_previous_df)
    assert res.summary.added == 0
    assert res.summary.deleted == 0
    assert res.summary.modified == 0
    assert res.summary.unchanged == len(valid_previous_df)
    assert len(res.unchanged) == len(valid_previous_df)


def test_tc02_all_records_in_current_only(valid_previous_df):
    """TC-02: All records in current only -> All ADDED; deleted=0."""
    empty_prev = pd.DataFrame(columns=valid_previous_df.columns)
    res = comparator.compare(empty_prev, valid_previous_df)
    assert res.summary.added == len(valid_previous_df)
    assert res.summary.deleted == 0
    assert res.summary.modified == 0
    assert res.summary.unchanged == 0


def test_tc03_all_records_in_previous_only(valid_previous_df):
    """TC-03: All records in previous only -> All DELETED; added=0."""
    empty_curr = pd.DataFrame(columns=valid_previous_df.columns)
    res = comparator.compare(valid_previous_df, empty_curr)
    assert res.summary.added == 0
    assert res.summary.deleted == len(valid_previous_df)
    assert res.summary.modified == 0
    assert res.summary.unchanged == 0


def test_tc04_one_field_changed_in_one_record(valid_previous_df):
    """TC-04: One field changed in one record -> MODIFIED; diff shows changed field."""
    curr_df = valid_previous_df.copy()
    curr_df.loc[curr_df["record_id"] == "SYN-001", "name"] = "Arjun K. Mehta"

    res = comparator.compare(valid_previous_df, curr_df)
    assert res.summary.modified == 1
    assert res.summary.unchanged == len(valid_previous_df) - 1
    mod = res.modified[0]
    assert mod.record_id == "SYN-001"
    assert "name" in mod.changed_fields
    assert any(d.field == "name" and d.previous_value == "Arjun Mehta" and d.current_value == "Arjun K. Mehta" for d in mod.diffs)


def test_tc05_all_fields_unchanged_for_record(valid_previous_df):
    """TC-05: All fields unchanged for a record -> That record UNCHANGED."""
    res = comparator.compare(valid_previous_df, valid_previous_df)
    unchanged_ids = {r.record_id for r in res.unchanged}
    assert "SYN-001" in unchanged_ids


def test_tc06_duplicate_record_id_in_previous():
    """TC-06: Duplicate record_id in previous -> Those rows in ambiguous_previous."""
    prev_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
        {"record_id": "SYN-001", "name": "Arjun 2", "area_id": "A01", "area_name": "North"},
        {"record_id": "SYN-002", "name": "Priya", "area_id": "A01", "area_name": "North"},
    ])
    curr_df = pd.DataFrame([
        {"record_id": "SYN-002", "name": "Priya", "area_id": "A01", "area_name": "North"},
    ])
    res = comparator.compare(prev_df, curr_df)
    assert res.summary.ambiguous_previous == 2
    assert len(res.ambiguous_previous) == 2


def test_tc07_null_record_id_in_current():
    """TC-07: Null record_id in current -> That row in ambiguous_current."""
    prev_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
    ])
    curr_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
        {"record_id": None, "name": "No ID", "area_id": "A01", "area_name": "North"},
    ])
    res = comparator.compare(prev_df, curr_df)
    assert res.summary.ambiguous_current == 1
    assert len(res.ambiguous_current) == 1


def test_tc08_both_dataframes_empty():
    """TC-08: Both DataFrames empty -> All counts are 0."""
    empty = pd.DataFrame(columns=["record_id", "name", "area_id", "area_name"])
    res = comparator.compare(empty, empty)
    assert res.summary.previous_records == 0
    assert res.summary.current_records == 0
    assert res.summary.added == 0
    assert res.summary.deleted == 0
    assert res.summary.modified == 0
    assert res.summary.unchanged == 0


def test_tc09_multiple_fields_changed(valid_previous_df):
    """TC-09: Multiple fields changed -> MODIFIED; diffs list all changed fields."""
    curr_df = valid_previous_df.copy()
    curr_df.loc[curr_df["record_id"] == "SYN-001", "age"] = 35
    curr_df.loc[curr_df["record_id"] == "SYN-001", "area_id"] = "A02"

    res = comparator.compare(valid_previous_df, curr_df)
    mod = res.modified[0]
    assert mod.record_id == "SYN-001"
    assert set(mod.changed_fields) == {"age", "area_id"}
    assert len(mod.diffs) == 2


def test_tc10_count_consistency_verified(valid_previous_df, valid_current_df):
    """TC-10: Count consistency verified -> Invariant equations hold."""
    res = comparator.compare(valid_previous_df, valid_current_df)
    issues = comparator.verify_count_consistency(res)
    assert len(issues) == 0


def test_tc11_nan_vs_nan_not_a_diff():
    """TC-11: NaN vs NaN in same field -> Not counted as a diff."""
    df1 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North", "age": None}
    ])
    df2 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North", "age": None}
    ])
    res = comparator.compare(df1, df2)
    assert res.summary.modified == 0
    assert res.summary.unchanged == 1


def test_tc12_nan_vs_real_value_counted_as_diff():
    """TC-12: NaN vs real value in same field -> Counted as a diff."""
    df1 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North", "age": None}
    ])
    df2 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North", "age": 30}
    ])
    res = comparator.compare(df1, df2)
    assert res.summary.modified == 1
    assert res.modified[0].changed_fields == ["age"]


def test_tc13_formatting_only_differences_are_unchanged():
    """TC-13: Formatting-only case/whitespace differences -> Classified as UNCHANGED."""
    df1 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Alice Smith", "area_id": "A01", "area_name": "North"}
    ])
    df2 = pd.DataFrame([
        {"record_id": "SYN-001", "name": "  alice   smith  ", "area_id": "A01", "area_name": "North"}
    ])
    res = comparator.compare(df1, df2)
    assert res.summary.modified == 0
    assert res.summary.unchanged == 1

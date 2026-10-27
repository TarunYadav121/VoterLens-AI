"""
conftest.py — VoterLens AI
===========================
Shared pytest fixtures for the backend test suite.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Ensure backend root is in sys.path regardless of working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
import pandas as pd

from app import create_app
import config as cfg
import comparator
import detector
import explainer
from models import ComparisonResult, StoredAnalysis


@pytest.fixture
def valid_previous_df() -> pd.DataFrame:
    """Standard valid previous dataset."""
    return pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun Mehta", "age": 34, "gender": "M", "area_id": "A01", "area_name": "North Valley", "area_type": "urban", "population_group": "group-1"},
        {"record_id": "SYN-002", "name": "Priya Sharma", "age": 29, "gender": "F", "area_id": "A01", "area_name": "North Valley", "area_type": "urban", "population_group": "group-1"},
        {"record_id": "SYN-003", "name": "Ravi Kumar", "age": 45, "gender": "M", "area_id": "B01", "area_name": "South Bend", "area_type": "rural", "population_group": "group-2"},
        {"record_id": "SYN-004", "name": "Kavya Nair", "age": 30, "gender": "F", "area_id": "B01", "area_name": "South Bend", "area_type": "rural", "population_group": "group-2"},
    ])


@pytest.fixture
def valid_current_df() -> pd.DataFrame:
    """Current dataset with 1 added, 1 deleted, 1 modified, 1 unchanged."""
    return pd.DataFrame([
        # SYN-001 is UNCHANGED
        {"record_id": "SYN-001", "name": "Arjun Mehta", "age": 34, "gender": "M", "area_id": "A01", "area_name": "North Valley", "area_type": "urban", "population_group": "group-1"},
        # SYN-002 is MODIFIED (age changed from 29 to 30)
        {"record_id": "SYN-002", "name": "Priya Sharma", "age": 30, "gender": "F", "area_id": "A01", "area_name": "North Valley", "area_type": "urban", "population_group": "group-1"},
        # SYN-003 is DELETED (omitted here)
        # SYN-004 is UNCHANGED
        {"record_id": "SYN-004", "name": "Kavya Nair", "age": 30, "gender": "F", "area_id": "B01", "area_name": "South Bend", "area_type": "rural", "population_group": "group-2"},
        # SYN-005 is ADDED
        {"record_id": "SYN-005", "name": "Amit Patel", "age": 22, "gender": "M", "area_id": "A01", "area_name": "North Valley", "area_type": "urban", "population_group": "group-1"},
    ])


@pytest.fixture
def valid_previous_csv_bytes(valid_previous_df) -> bytes:
    buf = io.StringIO()
    valid_previous_df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def valid_current_csv_bytes(valid_current_df) -> bytes:
    buf = io.StringIO()
    valid_current_df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def clean_comparison_result(valid_previous_df) -> ComparisonResult:
    """Comparison of identical DataFrames producing zero diffs/anomalies."""
    return comparator.compare(valid_previous_df, valid_previous_df)


@pytest.fixture
def active_comparison_result(valid_previous_df, valid_current_df) -> ComparisonResult:
    return comparator.compare(valid_previous_df, valid_current_df)


@pytest.fixture
def flask_app():
    app = create_app(testing=True)
    return app


@pytest.fixture
def flask_client(flask_app):
    return flask_app.test_client()

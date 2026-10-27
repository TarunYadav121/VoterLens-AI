"""
test_detector.py — VoterLens AI
================================
Automated tests for detector.py covering scenarios TD-01 through TD-10.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import pytest

import comparator
import config as cfg
import data_generator
import detector


def _build_multi_area_data(num_areas: int = 10, records_per_area: int = 50):
    prev_rows = []
    curr_rows = []
    for i in range(1, num_areas + 1):
        aid = f"A{i:02d}"
        for j in range(records_per_area):
            rid = f"REC-{aid}-{j:03d}"
            row = {
                "record_id": rid,
                "name": f"Citizen {j}",
                "age": 30,
                "gender": "M",
                "area_id": aid,
                "area_name": f"Area {aid}",
                "area_type": "urban",
                "population_group": "group-1",
            }
            prev_rows.append(dict(row))
            curr_rows.append(dict(row))
    return pd.DataFrame(prev_rows), pd.DataFrame(curr_rows)


def test_td01_clean_dataset_zero_findings():
    """TD-01: Clean dataset -> Zero findings."""
    clean_prev, clean_curr = data_generator.generate_clean_datasets()
    res = comparator.compare(clean_prev, clean_curr)
    findings, _ = detector.detect(res)
    assert len(findings) == 0


def test_td02_removal_rate_above_threshold():
    """TD-02: Area with removal rate > threshold -> Finding RULE-D-007 emitted."""
    prev_df, curr_df = _build_multi_area_data(num_areas=10, records_per_area=50)
    # In area A01, remove 30 records (60% removal rate vs 0% baseline)
    to_delete = {f"REC-A01-{j:03d}" for j in range(30)}
    curr_df = curr_df[~curr_df["record_id"].isin(to_delete)].reset_index(drop=True)

    res = comparator.compare(prev_df, curr_df)
    findings, area_stats = detector.detect(res)

    rule_7_findings = [f for f in findings if f.rule_id == "RULE-D-007"]
    assert len(rule_7_findings) >= 1
    assert any(f.affected_area_id == "A01" for f in rule_7_findings)


def test_td03_removal_rate_equal_threshold():
    """TD-03: Area with removal rate = threshold -> Triggers if >= threshold."""
    prev_df, curr_df = _build_multi_area_data(num_areas=10, records_per_area=100)
    # Remove exactly 20 records from A01 (20% vs baseline 0%)
    to_delete = {f"REC-A01-{j:03d}" for j in range(20)}
    curr_df = curr_df[~curr_df["record_id"].isin(to_delete)].reset_index(drop=True)

    res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(res)
    assert any(f.rule_id == "RULE-D-007" and f.affected_area_id == "A01" for f in findings)


def test_td04_removal_rate_below_threshold():
    """TD-04: Area with removal rate < threshold -> No finding for RULE-D-007."""
    prev_df, curr_df = _build_multi_area_data(num_areas=10, records_per_area=100)
    # Remove only 5 records (5% < 20% threshold)
    to_delete = {f"REC-A01-{j:03d}" for j in range(5)}
    curr_df = curr_df[~curr_df["record_id"].isin(to_delete)].reset_index(drop=True)

    res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(res)
    assert not any(f.rule_id == "RULE-D-007" and f.affected_area_id == "A01" for f in findings)


def test_td05_addition_rate_above_threshold():
    """TD-05: Area with addition rate > threshold -> Finding RULE-D-008 emitted."""
    prev_df, curr_df = _build_multi_area_data(num_areas=10, records_per_area=50)
    # Add 25 new records to A01 (50% addition rate vs 0% baseline)
    new_records = []
    for k in range(25):
        new_records.append({
            "record_id": f"NEW-A01-{k:03d}",
            "name": f"New Citizen {k}",
            "age": 25,
            "gender": "F",
            "area_id": "A01",
            "area_name": "Area A01",
            "area_type": "urban",
            "population_group": "group-1",
        })
    curr_df = pd.concat([curr_df, pd.DataFrame(new_records)], ignore_index=True)

    res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(res)
    assert any(f.rule_id == "RULE-D-008" and f.affected_area_id == "A01" for f in findings)


def test_td06_zero_previous_records_safe_division():
    """TD-06: Zero previous records in one area -> Removal rate is None; no division error."""
    prev_df = pd.DataFrame([
        {"record_id": "REC-1", "name": "Citizen 1", "area_id": "A01", "area_name": "Area A01"}
    ])
    curr_df = pd.DataFrame([
        {"record_id": "REC-1", "name": "Citizen 1", "area_id": "A01", "area_name": "Area A01"},
        {"record_id": "REC-2", "name": "Citizen 2", "area_id": "B01", "area_name": "Area B01"},
    ])
    res = comparator.compare(prev_df, curr_df)
    findings, area_stats = detector.detect(res)
    b01_stat = next(s for s in area_stats if s.area_id == "B01")
    assert b01_stat.removal_rate_pct is None


def test_td07_missing_area_type_counterfactual():
    """TD-07: Missing area_type for area -> Similar-area returns warning/insufficient data."""
    stat = detector.AreaStat(
        area_id="X01", area_name="Area X", previous_count=50, current_count=50,
        added_count=0, deleted_count=0, modified_count=0, unchanged_count=50, net_change=0,
        removal_rate_pct=0.0, addition_rate_pct=0.0
    )
    res = detector.compute_counterfactual([stat], "X01", comparison_method="similar_areas")
    assert len(res.get("warnings", [])) > 0


def test_td08_comparison_group_below_min_size():
    """TD-08: Comparison group < MIN_COMPARISON_GROUP_SIZE -> INSUFFICIENT_DATA warning."""
    stats = [
        detector.AreaStat(
            area_id="X01", area_name="Area X", area_type="rural", previous_count=50, current_count=50,
            added_count=0, deleted_count=0, modified_count=0, unchanged_count=50, net_change=0,
            removal_rate_pct=10.0, addition_rate_pct=0.0
        ),
        detector.AreaStat(
            area_id="X02", area_name="Area X2", area_type="rural", previous_count=50, current_count=50,
            added_count=0, deleted_count=0, modified_count=0, unchanged_count=50, net_change=0,
            removal_rate_pct=10.0, addition_rate_pct=0.0
        ),
    ]
    res = detector.compute_counterfactual(stats, "X01", comparison_method="similar_areas")
    assert any("Insufficient comparison group" in w for w in res.get("warnings", []))


def test_td09_duplicate_id_finding():
    """TD-09: Duplicate ID in file -> Finding RULE-D-001 emitted."""
    prev_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
        {"record_id": "SYN-001", "name": "Arjun Copy", "area_id": "A01", "area_name": "North"},
    ])
    curr_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
    ])
    res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(res)
    assert any(f.rule_id == "RULE-D-001" for f in findings)


def test_td10_missing_required_value_finding():
    """TD-10: Ambiguous record without record_id -> Finding RULE-D-002 emitted."""
    prev_df = pd.DataFrame([
        {"record_id": None, "name": "Arjun", "area_id": "A01", "area_name": "North"},
    ])
    curr_df = pd.DataFrame([
        {"record_id": "SYN-001", "name": "Arjun", "area_id": "A01", "area_name": "North"},
    ])
    res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(res)
    assert any(f.rule_id == "RULE-D-002" for f in findings)

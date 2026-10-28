from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

import comparator


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "backend" / "data"


FIELDS = [
    "record_id",
    "name",
    "area_id",
    "area_name",
    "age",
    "gender",
    "area_type",
    "population_group",
    "administrative_category",
    "polling_station_id",
    "registration_date",
]


def _row(record_id: str, area_id: str = "A01", age: int = 30, name: str = "Test Person"):
    return {
        "record_id": record_id,
        "name": name,
        "area_id": area_id,
        "area_name": f"Area {area_id}",
        "age": age,
        "gender": "F",
        "area_type": "urban",
        "population_group": "group-1",
        "administrative_category": "ward",
        "polling_station_id": f"PS-{area_id}-01",
        "registration_date": "2024-01-01",
    }


def _csv(rows):
    return pd.DataFrame(rows, columns=FIELDS).to_csv(index=False).encode("utf-8")


def _upload(client, previous_rows, current_rows):
    return client.post(
        "/api/analyze",
        data={
            "previous_file": (io.BytesIO(_csv(previous_rows)), "previous.csv"),
            "current_file": (io.BytesIO(_csv(current_rows)), "current.csv"),
        },
        content_type="multipart/form-data",
    )


def test_category_invariants_and_disjoint_record_ids(valid_previous_df, valid_current_df):
    result = comparator.compare(valid_previous_df, valid_current_df)
    summary = result.summary

    assert summary.previous_records == (
        summary.deleted + summary.modified + summary.unchanged + summary.ambiguous_previous
    )
    assert summary.current_records == (
        summary.added + summary.modified + summary.unchanged + summary.ambiguous_current
    )

    categories = [
        {record.record_id for record in result.added},
        {record.record_id for record in result.deleted},
        {record.record_id for record in result.modified},
        {record.record_id for record in result.unchanged},
    ]
    for left_index, left in enumerate(categories):
        for right in categories[left_index + 1 :]:
            assert left.isdisjoint(right)


def test_hand_made_pair_has_exact_categories():
    previous = pd.DataFrame([_row("V001"), _row("V002"), _row("V003", age=28)])
    current = pd.DataFrame([_row("V001"), _row("V003", age=29), _row("V004")])
    result = comparator.compare(previous, current)

    assert [record.record_id for record in result.unchanged] == ["V001"]
    assert [record.record_id for record in result.deleted] == ["V002"]
    assert [record.record_id for record in result.modified] == ["V003"]
    assert [record.record_id for record in result.added] == ["V004"]


def test_area_removal_rates_are_deleted_over_previous_count():
    previous = pd.DataFrame(
        [
            _row("A-1", "A01"),
            _row("A-2", "A01"),
            _row("B-1", "B01"),
            _row("B-2", "B01"),
            _row("B-3", "B01"),
        ]
    )
    current = pd.DataFrame([_row("A-1", "A01"), _row("B-1", "B01"), _row("B-2", "B01")])
    stats = {stat.area_id: stat for stat in comparator.compare(previous, current).area_stats}

    assert stats["A01"].removal_rate_pct == 50.0
    assert stats["B01"].removal_rate_pct == pytest.approx(33.33)


def test_comparison_is_deterministic(valid_previous_df, valid_current_df):
    first = comparator.compare(valid_previous_df, valid_current_df).model_dump()
    second = comparator.compare(valid_previous_df, valid_current_df).model_dump()
    assert first == second


def test_recheck_reproduces_original_finding(flask_client):
    response = _upload(
        flask_client,
        [_row("V001", "A01"), _row("V002", "B01")],
        [_row("V001", "A01", age=31)],
    )
    assert response.status_code == 200, response.get_json()
    analysis = response.get_json()
    finding = analysis["findings"][0]

    recheck = flask_client.post(
        "/api/recheck-finding",
        json={"analysis_id": analysis["analysis_id"], "finding_id": finding["finding_id"]},
    )
    payload = recheck.get_json()
    assert recheck.status_code == 200, payload
    assert payload["match"] is True
    assert payload["recheck_finding"]["rule_id"] == finding["rule_id"]
    assert payload["recheck_finding"]["affected_record_count"] == finding["affected_record_count"]


def test_counterfactual_all_areas_and_similar_areas(flask_client):
    previous = [_row("A01-1", "A01"), _row("A01-2", "A01")]
    previous += [_row("B01-1", "B01"), _row("B01-2", "B01")]
    previous += [_row("C01-1", "C01"), _row("C01-2", "C01")]
    previous += [_row("D01-1", "D01"), _row("D01-2", "D01")]
    current = [_row("A01-1", "A01"), _row("B01-1", "B01"), _row("B01-2", "B01")]
    current += [_row("C01-1", "C01"), _row("C01-2", "C01")]
    current += [_row("D01-1", "D01"), _row("D01-2", "D01")]

    response = _upload(flask_client, previous, current)
    assert response.status_code == 200, response.get_json()
    analysis_id = response.get_json()["analysis_id"]

    all_areas = flask_client.post(
        "/api/compare-areas",
        json={"analysis_id": analysis_id, "area_id": "A01", "comparison_method": "all_areas"},
    )
    all_payload = all_areas.get_json()
    assert all_areas.status_code == 200, all_payload
    assert all_payload["new_comparison"]["group_size"] == 3
    assert all_payload["new_comparison"]["baseline_rate_pct"] == pytest.approx(0.0)

    similar = flask_client.post(
        "/api/compare-areas",
        json={"analysis_id": analysis_id, "area_id": "A01", "comparison_method": "similar_areas"},
    )
    similar_payload = similar.get_json()
    assert similar.status_code == 200, similar_payload
    assert similar_payload["new_comparison"]["group_size"] == 3

    too_few = _upload(flask_client, [_row("X1", "X01"), _row("Y1", "Y01")], [_row("X1", "X01")])
    assert too_few.status_code == 200, too_few.get_json()
    insufficient = flask_client.post(
        "/api/compare-areas",
        json={
            "analysis_id": too_few.get_json()["analysis_id"],
            "area_id": "X01",
            "comparison_method": "similar_areas",
        },
    )
    insufficient_payload = insufficient.get_json()
    assert insufficient.status_code == 200, insufficient_payload
    assert any("Insufficient comparison group" in warning for warning in insufficient_payload["warnings"])


def test_requested_sample_fixture_counts_are_present():
    previous_path = DATA_DIR / "roll_before.csv"
    current_path = DATA_DIR / "roll_after.csv"
    if not previous_path.exists() or not current_path.exists():
        pytest.fail("Requested fixtures backend/data/roll_before.csv and roll_after.csv are missing")

    previous = pd.read_csv(previous_path)
    current = pd.read_csv(current_path)
    assert len(previous) == 300
    assert len(current) == 280

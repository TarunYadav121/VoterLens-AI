from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

import comparator
import config as cfg
from validator import validate_and_load


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


def row(record_id: str, area_id: str = "A01", age: int = 30, name: str = "Test Person"):
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


def csv_bytes(rows, columns=FIELDS) -> bytes:
    frame = pd.DataFrame(rows, columns=columns)
    return frame.to_csv(index=False).encode("utf-8")


def upload(client, previous_rows, current_rows, previous_name="previous.csv", current_name="current.csv"):
    return client.post(
        "/api/analyze",
        data={
            "previous_file": (io.BytesIO(csv_bytes(previous_rows)), previous_name),
            "current_file": (io.BytesIO(csv_bytes(current_rows)), current_name),
        },
        content_type="multipart/form-data",
    )


def test_summary_invariants_and_disjoint_categories(valid_previous_df, valid_current_df):
    result = comparator.compare(valid_previous_df, valid_current_df)
    summary = result.summary.model_dump()

    assert summary["previous_records"] == (
        summary["deleted"]
        + summary["modified"]
        + summary["unchanged"]
        + summary["ambiguous_previous"]
    )
    assert summary["current_records"] == (
        summary["added"]
        + summary["modified"]
        + summary["unchanged"]
        + summary["ambiguous_current"]
    )

    categories = {
        "added": {r.record_id for r in result.added},
        "deleted": {r.record_id for r in result.deleted},
        "modified": {r.record_id for r in result.modified},
        "unchanged": {r.record_id for r in result.unchanged},
    }
    for left_name, left in categories.items():
        for right_name, right in categories.items():
            if left_name != right_name:
                assert left.isdisjoint(right), (left_name, right_name)


def test_known_hand_made_pair_has_exact_categories():
    previous = pd.DataFrame([row("V001"), row("V002"), row("V003", age=28)])
    current = pd.DataFrame([row("V001"), row("V003", age=29), row("V004")])
    result = comparator.compare(previous, current)

    assert [r.record_id for r in result.unchanged] == ["V001"]
    assert [r.record_id for r in result.deleted] == ["V002"]
    assert [r.record_id for r in result.modified] == ["V003"]
    assert [r.record_id for r in result.added] == ["V004"]


def test_area_removal_rate_is_deleted_over_previous_count():
    previous = pd.DataFrame(
        [row("A-1", "A01"), row("A-2", "A01"), row("B-1", "B01"), row("B-2", "B01"), row("B-3", "B01"),
         row("C-1", "C01"), row("C-2", "C01"), row("C-3", "C01"), row("C-4", "C01")]
    )
    current = pd.DataFrame(
        [row("A-1", "A01"), row("B-1", "B01"), row("B-2", "B01"),
         row("C-1", "C01"), row("C-2", "C01"), row("C-3", "C01")]
    )
    stats = {s.area_id: s for s in comparator.compare(previous, current).area_stats}
    assert stats["A01"].removal_rate_pct == 50.0
    assert stats["B01"].removal_rate_pct == pytest.approx(33.33)
    assert stats["C01"].removal_rate_pct == 25.0


def test_formatting_only_differences_are_unchanged():
    previous = pd.DataFrame([row("V001", name="Alice Smith")])
    current = pd.DataFrame([row("V001", name="  alice   smith  ")])
    result = comparator.compare(previous, current)
    assert [r.record_id for r in result.unchanged] == ["V001"]
    assert not result.modified


def test_sample_data_matches_expected_outcomes(flask_client):
    expected = json.loads(
        (Path(__file__).parents[2] / "data" / "expected_outcomes.json").read_text()
    )
    previous = (Path(__file__).parents[2] / "data" / "previous_roll.csv").read_bytes()
    current = (Path(__file__).parents[2] / "data" / "current_roll.csv").read_bytes()
    response = flask_client.post(
        "/api/analyze",
        data={
            "previous_file": (io.BytesIO(previous), "previous_roll.csv"),
            "current_file": (io.BytesIO(current), "current_roll.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    observed = {}
    for key in ("added_records", "deleted_records", "modified_records"):
        observed.update(
            {record["record_id"]: record["change_category"] for record in body["changes"][key]["records"]}
        )
    assert {key: expected[key] for key in observed} == observed


def test_recheck_reports_dataset_and_config_change_status(flask_client):
    response = upload(
        flask_client,
        [row("V001", "A01"), row("V002", "B01")],
        [row("V001", "A01", age=31)],
    )
    assert response.status_code == 200
    body = response.get_json()
    finding = body["findings"][0]
    recheck = flask_client.post(
        "/api/recheck-finding",
        json={"analysis_id": body["analysis_id"], "finding_id": finding["finding_id"]},
    )
    assert recheck.status_code == 200
    payload = recheck.get_json()
    assert "dataset_changed" in payload
    assert "config_changed" in payload


def test_counterfactual_small_group_reports_insufficient_data(flask_client):
    response = upload(
        flask_client,
        [row("V001", "A01"), row("V002", "B01"), row("V003", "C01")],
        [row("V001", "A01"), row("V002", "B01"), row("V003", "C01")],
    )
    assert response.status_code == 200
    body = response.get_json()
    result = flask_client.post(
        "/api/compare-areas",
        json={
            "analysis_id": body["analysis_id"],
            "area_id": "A01",
            "comparison_method": "similar_areas",
        },
    )
    assert result.status_code == 200
    payload = result.get_json()
    assert payload["warnings"]
    assert "Insufficient comparison group" in payload["warnings"][0]


@pytest.mark.parametrize(
    "previous,current,expected_code",
    [
        (b"", b"record_id,name,area_id,area_name,age,gender\n", "VALIDATION_FAILED"),
        (b"record_id,name\nV1,A\n", b"record_id,name\nV1,A\n", "VALIDATION_FAILED"),
        (b"not csv bytes", b"not csv bytes", "VALIDATION_FAILED"),
    ],
)
def test_bad_csv_inputs_are_structured_errors(flask_client, previous, current, expected_code):
    response = flask_client.post(
        "/api/analyze",
        data={
            "previous_file": (io.BytesIO(previous), "previous.csv"),
            "current_file": (io.BytesIO(current), "current.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code in (400, 413)
    assert response.is_json
    assert response.get_json()["code"] == expected_code


def test_non_numeric_threshold_is_structured_error(flask_client):
    response = upload(flask_client, [row("V001")], [row("V001")])
    assert response.status_code == 200
    analysis_id = response.get_json()["analysis_id"]
    result = flask_client.post(
        "/api/compare-areas",
        json={"analysis_id": analysis_id, "area_id": "A01", "threshold_override": "not-a-number"},
    )
    assert result.status_code == 400
    assert result.is_json


def test_duplicate_ids_are_ambiguous_warnings_not_matches(flask_client):
    previous = [row("DUP"), row("DUP", name="Second")]
    response = upload(flask_client, previous, [row("DUP")])
    assert response.status_code == 200
    assert response.is_json
    payload = response.get_json()
    assert payload["summary"]["ambiguous_previous"] == 2
    assert payload["summary"]["modified"] == 0
    assert payload["summary"]["added"] == 1
    assert any(f["rule_id"] == "RULE-D-001" for f in payload["findings"])

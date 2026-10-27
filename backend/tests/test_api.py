"""
test_api.py — VoterLens AI
===========================
Automated tests for Flask REST API routes (TA-01 through TA-11, and False-Alarm Challenge).
"""

import io
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest


def test_ta01_get_health(flask_client):
    """TA-01: GET /api/health -> 200, status: ok."""
    resp = flask_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


def test_ta02_post_analyze_valid_files(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-02: POST /api/analyze with valid files -> 200, summary counts consistent."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    resp = flask_client.post("/api/analyze", data=data)
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data["status"] == "success"
    assert "analysis_id" in res_data
    assert "summary" in res_data

    # Check summary consistency
    s = res_data["summary"]
    assert s["previous_records"] == s["deleted"] + s["modified"] + s["unchanged"] + s["ambiguous_previous"]
    assert s["current_records"] == s["added"] + s["modified"] + s["unchanged"] + s["ambiguous_current"]


def test_ta03_post_analyze_missing_previous_file(flask_client, valid_current_csv_bytes):
    """TA-03: POST /api/analyze missing previous_file -> 400, MISSING_FILE code."""
    data = {
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    resp = flask_client.post("/api/analyze", data=data)
    assert resp.status_code == 400
    res_data = resp.get_json()
    assert res_data["code"] == "MISSING_FILE"


def test_ta04_post_analyze_invalid_csv(flask_client, valid_current_csv_bytes):
    """TA-04: POST /api/analyze with invalid CSV -> 400, VALIDATION_FAILED code."""
    bad_csv = b"name,age\nArjun,30\n"  # missing record_id, area_id, area_name
    data = {
        "previous_file": (io.BytesIO(bad_csv), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    resp = flask_client.post("/api/analyze", data=data)
    assert resp.status_code == 400
    res_data = resp.get_json()
    assert res_data["code"] == "VALIDATION_FAILED"


def test_ta05_post_analyze_unsupported_file_type(flask_client):
    """TA-05: Unsupported file type -> 400, UNSUPPORTED_FILE_TYPE code."""
    data = {
        "previous_file": (io.BytesIO(b"data"), "previous_roll.xlsx"),
        "current_file": (io.BytesIO(b"data"), "current_roll.csv"),
    }
    resp = flask_client.post("/api/analyze", data=data)
    assert resp.status_code == 400
    res_data = resp.get_json()
    assert res_data["code"] == "UNSUPPORTED_FILE_TYPE"


def test_ta06_export_added_csv_success(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-06: GET /api/export/<id>/added -> 200, text/csv content type."""
    # Run analysis first
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    analysis_id = analyze_resp.get_json()["analysis_id"]

    resp = flask_client.get(f"/api/export/{analysis_id}/added")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type


def test_ta07_export_bad_id_not_found(flask_client):
    """TA-07: GET /api/export/<bad-id>/added -> 404, ANALYSIS_NOT_FOUND."""
    resp = flask_client.get("/api/export/ANALYSIS-DOESNOTEXIST/added")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "ANALYSIS_NOT_FOUND"


def test_ta08_challenge_run(flask_client):
    """TA-08: POST /api/challenge/run -> 200, calculated metrics and disclaimer."""
    resp = flask_client.post("/api/challenge/run")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["total_scenarios"] == 10
    assert "precision" in data
    assert "recall" in data
    assert "disclaimer" in data
    assert "synthetic scenarios" in data["disclaimer"].lower()


def test_ta09_recheck_finding(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-09: POST /api/recheck-finding -> 200, returns recheck status."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    res_data = analyze_resp.get_json()
    analysis_id = res_data["analysis_id"]

    # If findings present, test recheck
    if res_data["findings"]:
        finding_id = res_data["findings"][0]["finding_id"]
        recheck_resp = flask_client.post("/api/recheck-finding", json={
            "analysis_id": analysis_id,
            "finding_id": finding_id,
        })
        assert recheck_resp.status_code == 200
        assert recheck_resp.get_json()["status"] == "success"
    else:
        # Recheck non-existent finding returns 404
        recheck_resp = flask_client.post("/api/recheck-finding", json={
            "analysis_id": analysis_id,
            "finding_id": "FND-NONE",
        })
        assert recheck_resp.status_code == 404


def test_ta10_record_inspector(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-10: GET /api/record/<analysis_id>/<record_id> -> 200, detailed record diff."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    analysis_id = analyze_resp.get_json()["analysis_id"]

    # Check modified record SYN-002
    resp = flask_client.get(f"/api/record/{analysis_id}/SYN-002")
    assert resp.status_code == 200
    rec_data = resp.get_json()
    assert rec_data["record_id"] == "SYN-002"
    assert rec_data["change_category"] == "MODIFIED"
    assert "diffs" in rec_data
    assert "recommended_review_actions" in rec_data


def test_ta11_explain_qa(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-11: POST /api/explain-qa -> 200, multilingual assistant answers."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    res_data = analyze_resp.get_json()
    analysis_id = res_data["analysis_id"]

    if res_data["findings"]:
        finding_id = res_data["findings"][0]["finding_id"]
        qa_resp = flask_client.post("/api/explain-qa", json={
            "analysis_id": analysis_id,
            "finding_id": finding_id,
            "question_key": "why_flagged",
            "language": "simple",
        })
        assert qa_resp.status_code == 200
        assert "answer" in qa_resp.get_json()


def test_ta12_compare_areas_invalid_threshold(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-12: POST /api/compare-areas with non-numeric threshold -> 400 INVALID_THRESHOLD."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    analysis_id = analyze_resp.get_json()["analysis_id"]

    resp = flask_client.post("/api/compare-areas", json={
        "analysis_id": analysis_id,
        "area_id": "A01",
        "threshold_override": "not-a-number",
    })
    assert resp.status_code == 400
    res_data = resp.get_json()
    assert res_data["code"] == "INVALID_THRESHOLD"


def test_ta13_recheck_includes_change_flags(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-13: POST /api/recheck-finding returns dataset_changed and config_changed flags."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    res_data = analyze_resp.get_json()
    analysis_id = res_data["analysis_id"]

    # Trigger recheck (or test with dummy finding id for contract check)
    if res_data["findings"]:
        finding_id = res_data["findings"][0]["finding_id"]
        resp = flask_client.post("/api/recheck-finding", json={
            "analysis_id": analysis_id,
            "finding_id": finding_id,
        })
        assert resp.status_code == 200
        recheck_data = resp.get_json()
        assert "dataset_changed" in recheck_data
        assert "config_changed" in recheck_data
        assert isinstance(recheck_data["dataset_changed"], bool)
        assert isinstance(recheck_data["config_changed"], bool)


def test_ta14_unsupported_qa_question_refusal(flask_client, valid_previous_csv_bytes, valid_current_csv_bytes):
    """TA-14: POST /api/explain-qa with unsupported question returns evidence-grounded refusal."""
    data = {
        "previous_file": (io.BytesIO(valid_previous_csv_bytes), "previous_roll.csv"),
        "current_file": (io.BytesIO(valid_current_csv_bytes), "current_roll.csv"),
    }
    analyze_resp = flask_client.post("/api/analyze", data=data)
    res_data = analyze_resp.get_json()
    analysis_id = res_data["analysis_id"]

    if res_data["findings"]:
        finding_id = res_data["findings"][0]["finding_id"]
        resp = flask_client.post("/api/explain-qa", json={
            "analysis_id": analysis_id,
            "finding_id": finding_id,
            "question_key": "who_committed_fraud",
            "language": "simple",
        })
        assert resp.status_code == 200
        answer = resp.get_json()["answer"]
        assert "cannot answer that from this evidence" in answer.lower()
        assert "prove wrongdoing" in answer.lower()


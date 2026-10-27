"""
test_explainer.py — VoterLens AI
=================================
Automated tests for explainer.py covering scenarios TE-01 through TE-07.
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
import detector
import explainer


def test_te01_passport_rule_id_and_threshold():
    """TE-01: Passport generated for finding -> rule_id and threshold match."""
    finding = detector.Finding(
        finding_id="FND-RULE-D-007-B01",
        rule_id="RULE-D-007",
        category="AGGREGATE_PATTERN",
        title="High removal rate",
        description="Removal rate in B01 exceeds threshold",
        review_priority="HIGH",
        affected_record_count=15,
        affected_area_id="B01",
        affected_area_name="South Bend",
        threshold=cfg.THRESHOLD_REMOVAL_RATE,
        baseline=0.05,
        baseline_method="mean_of_all_areas",
        comparison_group_size=5,
    )
    comp_result = comparator.compare(
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "B01", "area_name": "South Bend"}]),
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "B01", "area_name": "South Bend"}]),
    )
    passport = explainer.build_evidence_passport(
        finding, comp_result, {"previous_file": "sha256:1", "current_file": "sha256:2"}, "ANALYSIS-TEST"
    )
    assert passport.detection_rule_id == "RULE-D-007"
    assert passport.threshold == cfg.THRESHOLD_REMOVAL_RATE
    assert passport.analysis_id == "ANALYSIS-TEST"


def test_te02_supporting_counts_match_comparator():
    """TE-02: Supporting counts match comparator output."""
    prev_df = pd.DataFrame([
        {"record_id": "SYN-1", "name": "A", "area_id": "B01", "area_name": "South"},
        {"record_id": "SYN-2", "name": "B", "area_id": "B01", "area_name": "South"},
    ])
    curr_df = pd.DataFrame([
        {"record_id": "SYN-1", "name": "A", "area_id": "B01", "area_name": "South"},
    ])
    comp_res = comparator.compare(prev_df, curr_df)
    findings, _ = detector.detect(comp_res)

    passports = explainer.build_evidence_passports(
        findings, comp_res, {"previous_file": "sha256:1", "current_file": "sha256:2"}, "ANALYSIS-TEST"
    )
    # Check that any generated passport accurately reflects deleted counts
    for p in passports:
        if "deleted_count" in p.supporting_evidence:
            assert p.supporting_evidence["deleted_count"] == len(comp_res.deleted)


def test_te03_alternative_explanations_non_empty():
    """TE-03: possible_alternative_explanations non-empty -> At least 3 present."""
    finding = detector.Finding(
        finding_id="FND-1",
        rule_id="RULE-D-007",
        category="AGGREGATE_PATTERN",
        title="High removal rate",
        description="High removal rate",
        review_priority="HIGH",
        affected_record_count=10,
        possible_explanations=[
            "Legitimate relocation",
            "Boundary revision",
            "Death audit",
        ],
    )
    comp_res = comparator.compare(
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "A01", "area_name": "A"}]),
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "A01", "area_name": "A"}]),
    )
    passport = explainer.build_evidence_passport(
        finding, comp_res, {"previous_file": "1", "current_file": "2"}, "ANALYSIS-1"
    )
    assert len(passport.possible_alternative_explanations) >= 3


def test_te04_limitations_section_present():
    """TE-04: Limitations section present -> Non-empty string."""
    finding = detector.Finding(
        finding_id="FND-1",
        rule_id="RULE-D-007",
        category="AGGREGATE_PATTERN",
        title="High removal rate",
        description="High removal rate",
        review_priority="HIGH",
        affected_record_count=10,
        limitations="Standard test limitation",
    )
    comp_res = comparator.compare(
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "A01", "area_name": "A"}]),
        pd.DataFrame([{"record_id": "1", "name": "A", "area_id": "A01", "area_name": "A"}]),
    )
    passport = explainer.build_evidence_passport(
        finding, comp_res, {"previous_file": "1", "current_file": "2"}, "ANALYSIS-1"
    )
    assert len(passport.limitations.strip()) > 0
    assert "signal for human review" in passport.limitations.lower()


def test_te05_fingerprint_generation():
    """TE-05: Fingerprint computation is deterministic and prefixed with sha256:."""
    content = b"test csv content for voterlens"
    fp1 = explainer.fingerprint(content)
    fp2 = explainer.fingerprint(content)
    assert fp1.startswith("sha256:")
    assert fp1 == fp2


def test_te06_multilingual_explanation():
    """TE-06: Multilingual explanations generate text for simple, technical, hindi."""
    finding = detector.Finding(
        finding_id="FND-1",
        rule_id="RULE-D-007",
        category="AGGREGATE_PATTERN",
        title="High removal rate",
        description="High removal rate",
        review_priority="HIGH",
        affected_record_count=10,
        affected_area_id="B01",
        affected_area_name="South Bend",
    )
    for qk in ["why_flagged", "what_evidence", "what_percentage", "what_verify", "does_prove_wrongdoing"]:
        for lang in ["simple", "technical", "hindi"]:
            ans = explainer.answer_question(finding, question_key=qk, language=lang)
            assert isinstance(ans, str)
            assert len(ans.strip()) > 0


def test_te07_disclaimer_always_non_accusatory():
    """TE-07: Disclaimer strictly declares signal for human review, not proof of wrongdoing."""
    finding = detector.Finding(
        finding_id="FND-1",
        rule_id="RULE-D-007",
        category="AGGREGATE_PATTERN",
        title="High removal rate",
        description="High removal rate",
        review_priority="HIGH",
        affected_record_count=10,
    )
    ans = explainer.answer_question(finding, "does_prove_wrongdoing", "simple")
    assert "does not prove wrongdoing" in ans.lower()

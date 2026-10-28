"""
test_reporter.py — VoterLens AI
================================
Automated tests for reporter.py covering scenarios TR-01 through TR-07.
"""

import io
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import pytest

import comparator
import detector
import explainer
from models import StoredAnalysis
import reporter


@pytest.fixture
def sample_stored_analysis(valid_previous_df, valid_current_df):
    comp_result = comparator.compare(valid_previous_df, valid_current_df)
    findings, area_stats = detector.detect(comp_result)
    comp_result.area_stats = area_stats
    passports = explainer.build_evidence_passports(
        findings, comp_result, {"previous_file": "sha256:p", "current_file": "sha256:c"}, "ANALYSIS-SAMPLE"
    )
    return StoredAnalysis(
        analysis_id="ANALYSIS-SAMPLE",
        analyzed_at="2026-10-27T18:00:00Z",
        dataset_fingerprints={"previous_file": "sha256:p", "current_file": "sha256:c"},
        validation_results={},
        comparison_result=comp_result,
        findings=findings,
        evidence_passports=passports,
    )


def test_tr01_export_added_csv(sample_stored_analysis):
    """TR-01: Export added CSV -> Row count matches summary.added."""
    csv_str = reporter.export_added_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == sample_stored_analysis.comparison_result.summary.added


def test_tr02_export_deleted_csv(sample_stored_analysis):
    """TR-02: Export deleted CSV -> Row count matches summary.deleted."""
    csv_str = reporter.export_deleted_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == sample_stored_analysis.comparison_result.summary.deleted


def test_tr03_export_modified_csv(sample_stored_analysis):
    """TR-03: Export modified CSV -> Row count matches summary.modified; includes diff info."""
    csv_str = reporter.export_modified_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == sample_stored_analysis.comparison_result.summary.modified
    assert "changed_fields" in df.columns
    assert "diff_summary" in df.columns


def test_tr04_export_findings_csv(sample_stored_analysis):
    """TR-04: Export findings CSV -> Row count matches len(findings)."""
    csv_str = reporter.export_findings_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == len(sample_stored_analysis.findings)


def test_tr05_export_area_comparison_csv(sample_stored_analysis):
    """TR-05: Export area_comparison CSV -> Row count matches distinct areas."""
    csv_str = reporter.export_area_comparison_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == len(sample_stored_analysis.comparison_result.area_stats)


def test_tr06_export_with_zero_results(clean_comparison_result):
    """TR-06: Export with zero results -> Valid CSV with header row only."""
    stored = StoredAnalysis(
        analysis_id="ANALYSIS-ZERO",
        analyzed_at="2026-10-27T18:00:00Z",
        dataset_fingerprints={},
        validation_results={},
        comparison_result=clean_comparison_result,
        findings=[],
        evidence_passports=[],
    )
    csv_str = reporter.export_added_csv(stored)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == 0
    assert "record_id" in df.columns


def test_tr07_export_summary_csv(sample_stored_analysis):
    """TR-07: Export summary CSV -> Exactly 1 row with matching counts."""
    csv_str = reporter.export_summary_csv(sample_stored_analysis)
    df = pd.read_csv(io.StringIO(csv_str))
    assert len(df) == 1
    assert df.iloc[0]["analysis_id"] == "ANALYSIS-SAMPLE"
    assert df.iloc[0]["added"] == sample_stored_analysis.comparison_result.summary.added


def test_record_export_escapes_spreadsheet_formula_prefix(sample_stored_analysis):
    sample_stored_analysis.comparison_result.added[0].data["name"] = "=HYPERLINK(\"https://example.test\")"
    csv_str = reporter.export_added_csv(sample_stored_analysis)
    assert "'=HYPERLINK" in csv_str

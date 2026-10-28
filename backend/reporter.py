"""
reporter.py — VoterLens AI
==========================
CSV export module.

Serializes stored analysis results to CSV bytes.
Reuses already-computed results from StoredAnalysis;
never independently recalculates.

Supported report types:
  - 'summary'         — One-row summary CSV
  - 'added'           — All added records
  - 'deleted'         — All deleted records
  - 'modified'        — All modified records with diffs
  - 'findings'        — All findings
  - 'area_comparison' — Per-area statistics
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from models import StoredAnalysis


def _safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula execution for user-controlled text."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _safe_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_csv_cell(value) for key, value in row.items()}


def export_summary_csv(stored: StoredAnalysis) -> str:
    """Generate summary CSV (one data row)."""
    output = io.StringIO()
    writer = csv.writer(output)
    s = stored.comparison_result.summary

    headers = [
        "analysis_id",
        "analyzed_at",
        "previous_records",
        "current_records",
        "added",
        "deleted",
        "modified",
        "unchanged",
        "ambiguous_previous",
        "ambiguous_current",
        "findings_count",
    ]
    writer.writerow(headers)
    writer.writerow([
        stored.analysis_id,
        stored.analyzed_at,
        s.previous_records,
        s.current_records,
        s.added,
        s.deleted,
        s.modified,
        s.unchanged,
        s.ambiguous_previous,
        s.ambiguous_current,
        len(stored.findings),
    ])
    return output.getvalue()


def export_added_csv(stored: StoredAnalysis) -> str:
    """Generate added records CSV."""
    output = io.StringIO()
    records = stored.comparison_result.added
    if not records:
        writer = csv.writer(output)
        writer.writerow(["record_id", "name", "area_id", "area_name", "age", "gender", "change_category"])
        return output.getvalue()

    # Collect all data keys across records to preserve column consistency
    sample_data = records[0].data if records[0].data else {}
    field_order = ["record_id", "change_category"] + [k for k in sample_data.keys() if k != "record_id"]

    writer = csv.DictWriter(output, fieldnames=field_order, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        row = dict(r.data)
        row["record_id"] = r.record_id
        row["change_category"] = r.change_category
        writer.writerow(_safe_csv_row(row))
    return output.getvalue()


def export_deleted_csv(stored: StoredAnalysis) -> str:
    """Generate deleted records CSV."""
    output = io.StringIO()
    records = stored.comparison_result.deleted
    if not records:
        writer = csv.writer(output)
        writer.writerow(["record_id", "name", "area_id", "area_name", "age", "gender", "change_category"])
        return output.getvalue()

    sample_data = records[0].data if records[0].data else {}
    field_order = ["record_id", "change_category"] + [k for k in sample_data.keys() if k != "record_id"]

    writer = csv.DictWriter(output, fieldnames=field_order, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        row = dict(r.data)
        row["record_id"] = r.record_id
        row["change_category"] = r.change_category
        writer.writerow(_safe_csv_row(row))
    return output.getvalue()


def _json_dumps(obj: Any) -> str:
    def _default(o: Any) -> Any:
        if hasattr(o, "item"):
            return o.item()
        try:
            import pandas as pd
            if pd.isna(o):
                return None
        except Exception:
            pass
        return str(o)
    return json.dumps(obj, ensure_ascii=False, default=_default)


def export_modified_csv(stored: StoredAnalysis) -> str:
    """Generate modified records CSV with diffs."""
    output = io.StringIO()
    records = stored.comparison_result.modified
    headers = [
        "record_id",
        "change_category",
        "changed_fields",
        "diff_summary",
        "previous_values_json",
        "current_values_json",
    ]
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in records:
        diff_str = "; ".join(
            f"{d.field}: {d.previous_value or 'null'} -> {d.current_value or 'null'}"
            for d in r.diffs
        )
        writer.writerow([_safe_csv_cell(value) for value in [
            r.record_id,
            r.change_category,
            ", ".join(r.changed_fields),
            diff_str,
            _json_dumps(r.previous_values),
            _json_dumps(r.current_values),
        ]])
    return output.getvalue()


def export_findings_csv(stored: StoredAnalysis) -> str:
    """Generate findings CSV."""
    output = io.StringIO()
    findings = stored.findings
    headers = [
        "finding_id",
        "rule_id",
        "category",
        "review_priority",
        "title",
        "affected_record_count",
        "affected_area_id",
        "affected_area_name",
        "threshold",
        "baseline",
        "baseline_method",
        "comparison_group_size",
        "description",
        "recommended_next_step",
        "detected_at",
    ]
    writer = csv.writer(output)
    writer.writerow(headers)

    for f in findings:
        writer.writerow([_safe_csv_cell(value) for value in [
            f.finding_id,
            f.rule_id,
            f.category,
            f.review_priority,
            f.title,
            f.affected_record_count,
            f.affected_area_id or "",
            f.affected_area_name or "",
            f.threshold if f.threshold is not None else "",
            f.baseline if f.baseline is not None else "",
            f.baseline_method or "",
            f.comparison_group_size if f.comparison_group_size is not None else "",
            f.description,
            f.recommended_next_step,
            f.detected_at,
        ]])
    return output.getvalue()


def export_area_comparison_csv(stored: StoredAnalysis) -> str:
    """Generate per-area statistics CSV."""
    output = io.StringIO()
    stats = stored.comparison_result.area_stats
    headers = [
        "area_id",
        "area_name",
        "area_type",
        "population_group",
        "previous_count",
        "current_count",
        "added_count",
        "deleted_count",
        "modified_count",
        "unchanged_count",
        "net_change",
        "removal_rate_pct",
        "addition_rate_pct",
        "baseline_removal_rate_pct",
        "baseline_addition_rate_pct",
        "baseline_method",
        "comparison_group_size",
        "removal_rate_diff_from_baseline_pct",
        "addition_rate_diff_from_baseline_pct",
        "flagged_removal",
        "flagged_addition",
        "finding_ids",
    ]
    writer = csv.writer(output)
    writer.writerow(headers)

    for s in stats:
        writer.writerow([_safe_csv_cell(value) for value in [
            s.area_id,
            s.area_name,
            s.area_type or "",
            s.population_group or "",
            s.previous_count,
            s.current_count,
            s.added_count,
            s.deleted_count,
            s.modified_count,
            s.unchanged_count,
            s.net_change,
            s.removal_rate_pct if s.removal_rate_pct is not None else "",
            s.addition_rate_pct if s.addition_rate_pct is not None else "",
            s.baseline_removal_rate_pct if s.baseline_removal_rate_pct is not None else "",
            s.baseline_addition_rate_pct if s.baseline_addition_rate_pct is not None else "",
            s.baseline_method,
            s.comparison_group_size,
            s.removal_rate_diff_from_baseline_pct if s.removal_rate_diff_from_baseline_pct is not None else "",
            s.addition_rate_diff_from_baseline_pct if s.addition_rate_diff_from_baseline_pct is not None else "",
            s.flagged_removal,
            s.flagged_addition,
            "; ".join(s.finding_ids),
        ]])
    return output.getvalue()


REPORT_EXPORTERS = {
    "summary": export_summary_csv,
    "added": export_added_csv,
    "deleted": export_deleted_csv,
    "modified": export_modified_csv,
    "findings": export_findings_csv,
    "area_comparison": export_area_comparison_csv,
}


def export_report_csv(stored: StoredAnalysis, report_type: str) -> tuple[str, str] | None:
    """
    Generate CSV content and filename for report_type.

    Returns (csv_content_str, filename) or None if report_type is invalid.
    """
    exporter = REPORT_EXPORTERS.get(report_type)
    if not exporter:
        return None

    csv_data = exporter(stored)
    filename = f"voterlens_{stored.analysis_id}_{report_type}.csv"
    return csv_data, filename

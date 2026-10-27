"""
detector.py — VoterLens AI
============================
Deterministic data-quality and aggregate-pattern detection engine.

Responsibilities:
  1. Apply all RULE-D-* rules to a ComparisonResult.
  2. Calculate area-level rates and compare against a configurable baseline.
  3. Update AreaStat objects with baseline and flag information.
  4. Emit structured Finding objects with supporting evidence.
  5. Never hard-code findings — all output is derived from input data.
  6. Use neutral language; never assert wrongdoing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from statistics import mean
from typing import Any

import pandas as pd

import config as cfg
from models import AreaStat, ComparisonResult, Finding


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding_id(rule_id: str, area_id: str | None = None) -> str:
    suffix = f"-{area_id}" if area_id else f"-{uuid.uuid4().hex[:6].upper()}"
    return f"FND-{rule_id}{suffix}"


# ---------------------------------------------------------------------------
# Baseline calculators
# ---------------------------------------------------------------------------

def _all_areas_removal_baseline(
    area_stats: list[AreaStat],
    exclude_area_id: str,
) -> tuple[float | None, int]:
    """
    Calculate mean removal rate across all areas except the selected one.

    Returns (baseline_rate_pct | None, group_size)
    """
    rates = [
        s.removal_rate_pct
        for s in area_stats
        if s.area_id != exclude_area_id and s.removal_rate_pct is not None
    ]
    if not rates:
        return None, 0
    return round(mean(rates), 4), len(rates)


def _all_areas_addition_baseline(
    area_stats: list[AreaStat],
    exclude_area_id: str,
) -> tuple[float | None, int]:
    rates = [
        s.addition_rate_pct
        for s in area_stats
        if s.area_id != exclude_area_id and s.addition_rate_pct is not None
    ]
    if not rates:
        return None, 0
    return round(mean(rates), 4), len(rates)


def _similar_areas_removal_baseline(
    area_stats: list[AreaStat],
    exclude_area_id: str,
    area_type: str | None,
    population_group: str | None,
) -> tuple[float | None, int, list[str]]:
    """
    Calculate mean removal rate among areas with the same area_type and
    population_group.

    Returns (baseline_rate_pct | None, group_size, filter_description)
    """
    filters_applied: list[str] = []
    candidates = [s for s in area_stats if s.area_id != exclude_area_id]

    if area_type:
        candidates = [s for s in candidates if s.area_type == area_type]
        filters_applied.append(f"area_type={area_type}")
    if population_group:
        candidates = [s for s in candidates if s.population_group == population_group]
        filters_applied.append(f"population_group={population_group}")

    rates = [s.removal_rate_pct for s in candidates if s.removal_rate_pct is not None]
    if len(rates) < cfg.MIN_COMPARISON_GROUP_SIZE:
        return None, len(rates), filters_applied
    return round(mean(rates), 4), len(rates), filters_applied


# ---------------------------------------------------------------------------
# Individual detection rules
# ---------------------------------------------------------------------------

def _detect_high_removal_rate(
    area_stats: list[AreaStat],
    findings: list[Finding],
) -> None:
    """RULE-D-007: Flag areas with removal rate substantially above baseline."""
    for stat in area_stats:
        if stat.removal_rate_pct is None:
            # Zero denominator — cannot compute rate
            continue

        baseline, group_size = _all_areas_removal_baseline(area_stats, stat.area_id)

        # Annotate the AreaStat with baseline info
        stat.baseline_removal_rate_pct = baseline
        stat.baseline_method = "mean_of_all_areas"
        stat.comparison_group_size = group_size

        if baseline is None:
            continue

        diff = round(stat.removal_rate_pct - baseline, 4)
        stat.removal_rate_diff_from_baseline_pct = diff

        threshold_pp = cfg.THRESHOLD_REMOVAL_RATE * 100  # convert to percentage points

        if diff >= threshold_pp:
            stat.flagged_removal = True
            fid = _finding_id("D-007", stat.area_id)
            stat.finding_ids.append(fid)

            rule = cfg.DETECTION_RULES["RULE-D-007"]

            findings.append(Finding(
                finding_id=fid,
                rule_id="RULE-D-007",
                category="AGGREGATE_PATTERN",
                title=f"Elevated Removal Rate — {stat.area_name} ({stat.area_id})",
                description=(
                    f"Area {stat.area_id} ({stat.area_name}) has a removal rate of "
                    f"{stat.removal_rate_pct:.1f}%, which is {diff:.1f} percentage points "
                    f"above the all-areas baseline of {baseline:.1f}% (group size: {group_size}). "
                    f"This exceeds the configured threshold of {threshold_pp:.1f} pp above baseline. "
                    f"Review the affected records and source data."
                ),
                review_priority="HIGH",
                affected_record_count=stat.deleted_count,
                affected_area_id=stat.area_id,
                affected_area_name=stat.area_name,
                supporting_evidence={
                    "area_previous_count": stat.previous_count,
                    "area_deleted_count": stat.deleted_count,
                    "area_removal_rate_pct": stat.removal_rate_pct,
                    "formula": f"{stat.deleted_count} / {stat.previous_count} * 100 = {stat.removal_rate_pct:.2f}%",
                    "baseline_removal_rate_pct": baseline,
                    "baseline_method": "mean_of_all_areas_excluding_selected",
                    "comparison_group_size": group_size,
                    "difference_from_baseline_pct": diff,
                    "threshold_pp_above_baseline": threshold_pp,
                },
                threshold=cfg.THRESHOLD_REMOVAL_RATE,
                baseline=baseline,
                baseline_method="mean_of_all_areas",
                comparison_group_size=group_size,
                possible_explanations=[
                    "Administrative boundary changes transferred records to a new area code.",
                    "Data-quality corrections removed duplicate or invalid entries from earlier versions.",
                    "Legitimate relocation of registered voters to other areas.",
                    "Mortality and normal attrition processed in bulk during this update cycle.",
                    "A data-entry error in the current version caused some records to be omitted.",
                ],
                recommended_next_step=(
                    f"Obtain the source enrollment documents for area {stat.area_id} and "
                    f"cross-reference each of the {stat.deleted_count} deleted record_ids "
                    "against the original registration ledger."
                ),
                limitations=(
                    "This finding is based on aggregate counts only. It does not examine "
                    "individual records, verify source data, or establish cause. The baseline "
                    "is the arithmetic mean and is sensitive to outliers in small datasets. "
                    "An anomaly flag is a signal for human review, not a conclusion."
                ),
                detected_at=_now(),
            ))


def _detect_high_addition_rate(
    area_stats: list[AreaStat],
    findings: list[Finding],
) -> None:
    """RULE-D-008: Flag areas with addition rate substantially above baseline."""
    for stat in area_stats:
        if stat.addition_rate_pct is None:
            continue

        baseline, group_size = _all_areas_addition_baseline(area_stats, stat.area_id)

        stat.baseline_addition_rate_pct = baseline
        if stat.baseline_method == "mean_of_all_areas":
            pass   # already set; don't overwrite if removal baseline was computed first

        if baseline is None:
            continue

        diff = round(stat.addition_rate_pct - baseline, 4)
        stat.addition_rate_diff_from_baseline_pct = diff

        threshold_pp = cfg.THRESHOLD_ADDITION_RATE * 100

        if diff >= threshold_pp:
            stat.flagged_addition = True
            fid = _finding_id("D-008", stat.area_id)
            stat.finding_ids.append(fid)

            findings.append(Finding(
                finding_id=fid,
                rule_id="RULE-D-008",
                category="AGGREGATE_PATTERN",
                title=f"Elevated Addition Rate — {stat.area_name} ({stat.area_id})",
                description=(
                    f"Area {stat.area_id} ({stat.area_name}) has an addition rate of "
                    f"{stat.addition_rate_pct:.1f}%, which is {diff:.1f} percentage points "
                    f"above the all-areas baseline of {baseline:.1f}% (group size: {group_size}). "
                    f"This exceeds the configured threshold of {threshold_pp:.1f} pp above baseline. "
                    f"Review the affected records and source data."
                ),
                review_priority="HIGH",
                affected_record_count=stat.added_count,
                affected_area_id=stat.area_id,
                affected_area_name=stat.area_name,
                supporting_evidence={
                    "area_current_count": stat.current_count,
                    "area_added_count": stat.added_count,
                    "area_addition_rate_pct": stat.addition_rate_pct,
                    "formula": f"{stat.added_count} / {stat.current_count} * 100 = {stat.addition_rate_pct:.2f}%",
                    "baseline_addition_rate_pct": baseline,
                    "baseline_method": "mean_of_all_areas_excluding_selected",
                    "comparison_group_size": group_size,
                    "difference_from_baseline_pct": diff,
                    "threshold_pp_above_baseline": threshold_pp,
                },
                threshold=cfg.THRESHOLD_ADDITION_RATE,
                baseline=baseline,
                baseline_method="mean_of_all_areas",
                comparison_group_size=group_size,
                possible_explanations=[
                    "New residential development in the area increased eligible voters.",
                    "Administrative boundary expansion merged adjacent areas into this one.",
                    "Bulk registration drive conducted in this area during the update period.",
                    "Records previously incorrectly filed under another area_id were corrected.",
                    "A data-entry error in the previous version caused some records to be missing.",
                ],
                recommended_next_step=(
                    f"Cross-reference the {stat.added_count} added records in area {stat.area_id} "
                    "against original enrollment forms and any boundary-change notifications."
                ),
                limitations=(
                    "This finding is based on aggregate counts only. It does not examine "
                    "individual records, verify source data, or establish cause. "
                    "An anomaly flag is a signal for human review, not a conclusion."
                ),
                detected_at=_now(),
            ))


def _detect_data_quality(
    comparison_result: ComparisonResult,
    findings: list[Finding],
) -> None:
    """
    RULE-D-001, D-002, D-003, D-004: Data-quality findings from comparator output.
    """
    s = comparison_result.summary

    # Ambiguous records split by duplicate vs missing required value (null ID)
    ambig_all = comparison_result.ambiguous_previous + comparison_result.ambiguous_current
    null_rows = [r for r in ambig_all if r.record_id is None]
    dup_rows = [r for r in ambig_all if r.record_id is not None]

    if dup_rows:
        fid = _finding_id("D-001")
        findings.append(Finding(
            finding_id=fid,
            rule_id="RULE-D-001",
            category="DATA_QUALITY",
            title="Duplicate Record Identifiers",
            description=(
                f"{len(dup_rows)} row(s) across files have duplicated record_id values "
                "and cannot be reliably matched."
            ),
            review_priority="MEDIUM",
            affected_record_count=len(dup_rows),
            supporting_evidence={
                "duplicate_rows": [
                    {"row_index": r.row_index, "record_id": r.record_id, "source": r.source_file}
                    for r in dup_rows[:10]
                ],
                "total_duplicates": len(dup_rows),
            },
            possible_explanations=[
                "Duplicate entries may reflect data-entry errors in the source system.",
            ],
            recommended_next_step=(
                "Review duplicate rows in the uploaded files and verify the correct record_id."
            ),
            limitations="Duplicate rows are excluded from change classification.",
            detected_at=_now(),
        ))

    if null_rows:
        fid = _finding_id("D-002")
        findings.append(Finding(
            finding_id=fid,
            rule_id="RULE-D-002",
            category="DATA_QUALITY",
            title="Missing Required Value (Identifier)",
            description=(
                f"{len(null_rows)} row(s) across files are missing record_id values "
                "and cannot be reliably matched."
            ),
            review_priority="MEDIUM",
            affected_record_count=len(null_rows),
            supporting_evidence={
                "missing_rows": [
                    {"row_index": r.row_index, "source": r.source_file}
                    for r in null_rows[:10]
                ],
                "total_missing": len(null_rows),
            },
            possible_explanations=[
                "Null identifiers may indicate rows added without an ID being assigned.",
            ],
            recommended_next_step=(
                "Review missing identifier rows and assign correct IDs from source registration documents."
            ),
            limitations="Rows with missing IDs are excluded from change classification.",
            detected_at=_now(),
        ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(
    comparison_result: ComparisonResult,
) -> tuple[list[Finding], list[AreaStat]]:
    """
    Run all detection rules against a ComparisonResult.

    Returns
    -------
    (findings, annotated_area_stats)
        findings            — list of Finding objects
        annotated_area_stats — AreaStat objects updated with baseline and flag info
    """
    findings: list[Finding] = []

    # Data-quality findings (from comparator output)
    _detect_data_quality(comparison_result, findings)

    # Aggregate-pattern findings (area-level)
    area_stats = comparison_result.area_stats
    _detect_high_removal_rate(area_stats, findings)
    _detect_high_addition_rate(area_stats, findings)

    return findings, area_stats


def compute_counterfactual(
    area_stats: list[AreaStat],
    target_area_id: str,
    comparison_method: str = "all_areas",
    threshold_override: float | None = None,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Re-run the area comparison for one area under different settings.
    Used by the Counterfactual Audit Lab endpoint.

    Returns a dict suitable for the CounterfactualResponse model.
    """
    target = next((s for s in area_stats if s.area_id == target_area_id), None)
    if target is None:
        return {"error": "AREA_NOT_FOUND", "area_id": target_area_id}

    threshold_pp = (threshold_override * 100) if threshold_override is not None \
        else (cfg.THRESHOLD_REMOVAL_RATE * 100)

    warnings: list[str] = []

    # Original comparison (all_areas, original threshold)
    orig_baseline, orig_n = _all_areas_removal_baseline(area_stats, target_area_id)
    orig_threshold_pp = cfg.THRESHOLD_REMOVAL_RATE * 100

    orig_diff = round(target.removal_rate_pct - orig_baseline, 4) \
        if (target.removal_rate_pct is not None and orig_baseline is not None) else None
    orig_flagged = (orig_diff is not None and orig_diff >= orig_threshold_pp)

    original_comparison: dict[str, Any] = {
        "method": "all_areas",
        "baseline_rate_pct": orig_baseline,
        "group_size": orig_n,
        "threshold_pp": orig_threshold_pp,
        "flagged": orig_flagged,
        "diff_from_baseline_pct": orig_diff,
    }

    # New comparison
    new_baseline: float | None = None
    new_n: int = 0
    filters_applied: list[str] = []

    if comparison_method == "similar_areas":
        f = filters or {}
        area_type_filter = f.get("area_type") or target.area_type
        pop_group_filter = f.get("population_group") or target.population_group

        if area_type_filter is None and pop_group_filter is None:
            warnings.append(
                "No area_type or population_group available for the selected area. "
                "Cannot compute similar-area baseline."
            )
        else:
            new_baseline, new_n, filters_applied = _similar_areas_removal_baseline(
                area_stats, target_area_id, area_type_filter, pop_group_filter
            )
            if new_baseline is None:
                warnings.append(
                    f"Insufficient comparison group (size={new_n}, "
                    f"minimum={cfg.MIN_COMPARISON_GROUP_SIZE}). "
                    "Similar-area baseline cannot be computed."
                )
    else:
        new_baseline, new_n = _all_areas_removal_baseline(area_stats, target_area_id)
        filters_applied = ["all_areas"]

    new_diff = round(target.removal_rate_pct - new_baseline, 4) \
        if (target.removal_rate_pct is not None and new_baseline is not None) else None
    new_flagged = (new_diff is not None and new_diff >= threshold_pp)

    new_comparison: dict[str, Any] = {
        "method": comparison_method,
        "filters_applied": dict(zip(["filter_" + str(i) for i in range(len(filters_applied))], filters_applied)),
        "baseline_rate_pct": new_baseline,
        "group_size": new_n,
        "threshold_pp": threshold_pp,
        "flagged": new_flagged,
        "diff_from_baseline_pct": new_diff,
    }

    status_changed = orig_flagged != new_flagged

    if status_changed:
        explanation = (
            f"Changing the comparison from {original_comparison['method']} "
            f"(baseline={orig_baseline:.1f}%, threshold={orig_threshold_pp:.1f} pp) "
            f"to {comparison_method} "
            f"(baseline={new_baseline:.1f}% if new_baseline else 'N/A'%, "
            f"threshold={threshold_pp:.1f} pp) "
            f"changed the flag status for area {target.area_name} from "
            f"{'FLAGGED' if orig_flagged else 'NOT FLAGGED'} to "
            f"{'FLAGGED' if new_flagged else 'NOT FLAGGED'}."
        )
    else:
        explanation = (
            f"Under the new comparison settings ({comparison_method}, "
            f"threshold={threshold_pp:.1f} pp), area {target.area_name} remains "
            f"{'FLAGGED' if new_flagged else 'NOT FLAGGED'}. "
            f"The difference from the new baseline is "
            f"{new_diff:.1f} pp." if new_diff is not None else "N/A."
        )

    return {
        "area_id": target.area_id,
        "area_name": target.area_name,
        "removal_rate_pct": target.removal_rate_pct,
        "original_comparison": original_comparison,
        "new_comparison": new_comparison,
        "status_changed": status_changed,
        "explanation": explanation,
        "warnings": warnings,
    }

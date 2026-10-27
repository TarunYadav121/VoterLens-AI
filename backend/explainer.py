"""
explainer.py — VoterLens AI
=============================
Evidence Passport generation and human-readable explanation module.

Responsibilities:
  1. Build an EvidencePassport for every significant Finding.
  2. Generate multilingual explanation text from templates.
  3. Support the Recheck Finding workflow.

Critical rules:
  - Never invent evidence or alter computed values.
  - All numeric values in a Passport must trace directly to comparator output.
  - Never assert wrongdoing; always include alternative explanations.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import config as cfg
from models import AreaStat, ComparisonResult, EvidencePassport, Finding


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Dataset fingerprinting
# ---------------------------------------------------------------------------

def fingerprint(file_bytes: bytes) -> str:
    """
    Compute SHA-256 fingerprint of raw file bytes.

    The fingerprint identifies the file but does NOT prove it is authentic
    or unmodified since its original publication. This limitation is always
    stated in the Evidence Passport.
    """
    return "sha256:" + hashlib.sha256(file_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Calculation detail builders
# ---------------------------------------------------------------------------

def _removal_rate_calculation(stat: AreaStat) -> dict[str, str]:
    rate = stat.removal_rate_pct
    baseline = stat.baseline_removal_rate_pct
    diff = stat.removal_rate_diff_from_baseline_pct
    threshold_pp = cfg.THRESHOLD_REMOVAL_RATE * 100

    steps = {
        "step_1": (
            f"Count DELETED records in area {stat.area_id}. "
            f"Result: {stat.deleted_count}"
        ),
        "step_2": (
            f"Count all valid records in the previous file where area_id == '{stat.area_id}'. "
            f"Result: {stat.previous_count}"
        ),
        "step_3": (
            f"removal_rate = {stat.deleted_count} / {stat.previous_count} * 100"
            + (f" = {rate:.2f}%" if rate is not None else " = N/A (zero denominator)")
        ),
        "step_4": (
            f"Compute baseline: mean removal rate of all other areas "
            f"(group size: {stat.comparison_group_size})."
            + (f" Result: {baseline:.2f}%" if baseline is not None else " Result: N/A")
        ),
        "step_5": (
            f"Difference = {rate:.2f} − {baseline:.2f} = {diff:.2f} pp"
            if (rate is not None and baseline is not None and diff is not None)
            else "Difference: N/A"
        ),
        "step_6": (
            f"Threshold check: {diff:.2f} pp ≥ {threshold_pp:.1f} pp threshold → rule triggered."
            if (diff is not None and diff >= threshold_pp)
            else f"Threshold check: {(f'{diff:.2f}' if diff is not None else 'N/A')} pp < {threshold_pp:.1f} pp → rule not triggered."
        ),
    }
    return steps


def _addition_rate_calculation(stat: AreaStat) -> dict[str, str]:
    rate = stat.addition_rate_pct
    baseline = stat.baseline_addition_rate_pct
    diff = stat.addition_rate_diff_from_baseline_pct
    threshold_pp = cfg.THRESHOLD_ADDITION_RATE * 100

    return {
        "step_1": (
            f"Count ADDED records in area {stat.area_id}. "
            f"Result: {stat.added_count}"
        ),
        "step_2": (
            f"Count all valid records in the current file where area_id == '{stat.area_id}'. "
            f"Result: {stat.current_count}"
        ),
        "step_3": (
            f"addition_rate = {stat.added_count} / {stat.current_count} * 100"
            + (f" = {rate:.2f}%" if rate is not None else " = N/A (zero denominator)")
        ),
        "step_4": (
            f"Compute baseline: mean addition rate of all other areas "
            f"(group size: {stat.comparison_group_size})."
            + (f" Result: {baseline:.2f}%" if baseline is not None else " Result: N/A")
        ),
        "step_5": (
            f"Difference = {rate:.2f} − {baseline:.2f} = {diff:.2f} pp"
            if (rate is not None and baseline is not None and diff is not None)
            else "Difference: N/A"
        ),
        "step_6": (
            f"Threshold check: {diff:.2f} pp ≥ {threshold_pp:.1f} pp threshold → rule triggered."
            if (diff is not None and diff >= threshold_pp)
            else f"Threshold check: {(f'{diff:.2f}' if diff is not None else 'N/A')} pp < {threshold_pp:.1f} pp → rule not triggered."
        ),
    }


# ---------------------------------------------------------------------------
# Config snapshot builder
# ---------------------------------------------------------------------------

def _config_snapshot() -> dict[str, Any]:
    return {
        "COMPARISON_FIELDS": cfg.COMPARISON_FIELDS,
        "THRESHOLD_REMOVAL_RATE": cfg.THRESHOLD_REMOVAL_RATE,
        "THRESHOLD_ADDITION_RATE": cfg.THRESHOLD_ADDITION_RATE,
        "MIN_COMPARISON_GROUP_SIZE": cfg.MIN_COMPARISON_GROUP_SIZE,
        "AGE_MIN_PLAUSIBLE": cfg.AGE_MIN_PLAUSIBLE,
        "AGE_MAX_PLAUSIBLE": cfg.AGE_MAX_PLAUSIBLE,
        "MAX_ROW_COUNT": cfg.MAX_ROW_COUNT,
    }


# ---------------------------------------------------------------------------
# Evidence Passport builder
# ---------------------------------------------------------------------------

def _area_stat_for_finding(
    finding: Finding,
    area_stats: list[AreaStat],
) -> AreaStat | None:
    if finding.affected_area_id:
        return next(
            (s for s in area_stats if s.area_id == finding.affected_area_id),
            None,
        )
    return None


def build_evidence_passport(
    finding: Finding,
    comparison_result: ComparisonResult,
    dataset_fingerprints: dict[str, str],
    analysis_id: str,
) -> EvidencePassport:
    """
    Build an EvidencePassport for a single Finding.

    All numeric values are taken from the Finding's supporting_evidence
    or from the ComparisonResult — never invented.
    """
    rule_info = cfg.DETECTION_RULES.get(finding.rule_id, {})
    area_stats = comparison_result.area_stats

    # Build calculation details
    calc_details: dict[str, str] = {}
    stat = _area_stat_for_finding(finding, area_stats)

    if finding.rule_id == "RULE-D-007" and stat:
        calc_details = _removal_rate_calculation(stat)
    elif finding.rule_id == "RULE-D-008" and stat:
        calc_details = _addition_rate_calculation(stat)
    else:
        # Generic calculation details from supporting evidence
        calc_details = {
            f"step_{i + 1}": f"{k}: {v}"
            for i, (k, v) in enumerate(finding.supporting_evidence.items())
        }

    # Fingerprint note
    fingerprint_note = (
        "SHA-256 fingerprints identify the specific files analysed. "
        "They do NOT prove the files are authentic or unmodified since "
        "their original publication. Independent chain-of-custody verification "
        "is required to establish file provenance."
    )

    return EvidencePassport(
        passport_id=f"EP-{finding.finding_id}",
        finding_id=finding.finding_id,
        category=finding.category,
        observation=finding.description,
        supporting_evidence=finding.supporting_evidence,
        detection_rule_id=finding.rule_id,
        detection_rule_name=rule_info.get("name", finding.rule_id),
        threshold=finding.threshold,
        threshold_units=(
            "percentage points above the comparison baseline"
            if finding.rule_id in ("RULE-D-007", "RULE-D-008")
            else ""
        ),
        baseline=finding.baseline,
        baseline_method=finding.baseline_method or "mean_of_all_areas",
        comparison_group_size=finding.comparison_group_size or 0,
        calculation_details=calc_details,
        dataset_fingerprints={
            **dataset_fingerprints,
            "fingerprint_note": fingerprint_note,
        },
        analysis_config=_config_snapshot(),
        possible_alternative_explanations=finding.possible_explanations,
        limitations=finding.limitations + (
            "\n\nThis finding does not prove wrongdoing. It is a signal for human review."
        ),
        recommended_next_steps=[finding.recommended_next_step] if finding.recommended_next_step else [],
        generated_at=_now(),
        analysis_id=analysis_id,
    )


def build_evidence_passports(
    findings: list[Finding],
    comparison_result: ComparisonResult,
    dataset_fingerprints: dict[str, str],
    analysis_id: str,
) -> list[EvidencePassport]:
    """Build Evidence Passports for all significant findings."""
    return [
        build_evidence_passport(f, comparison_result, dataset_fingerprints, analysis_id)
        for f in findings
    ]


# ---------------------------------------------------------------------------
# Multilingual explanation
# ---------------------------------------------------------------------------

def explain_finding(
    finding: Finding,
    language: str = "simple",
    area_stat: AreaStat | None = None,
) -> str:
    """
    Generate a human-readable explanation for a Finding in the requested language.

    Supported languages: "technical", "simple", "hindi"
    Falls back to "simple" for unknown languages.
    """
    lang = language if language in ("technical", "simple", "hindi") else "simple"

    rule_key = {
        "RULE-D-007": "HIGH_REMOVAL_RATE",
        "RULE-D-008": "HIGH_ADDITION_RATE",
    }.get(finding.rule_id)

    if rule_key and rule_key in cfg.EXPLANATION_TEMPLATES:
        template = cfg.EXPLANATION_TEMPLATES[rule_key][lang]
        ev = finding.supporting_evidence

        try:
            text = template.format(
                area_id=finding.affected_area_id or "N/A",
                area_name=finding.affected_area_name or "N/A",
                rate=ev.get("area_removal_rate_pct") or ev.get("area_addition_rate_pct") or 0.0,
                diff=ev.get("difference_from_baseline_pct", 0.0),
                method="all-areas mean",
                baseline=ev.get("baseline_removal_rate_pct") or ev.get("baseline_addition_rate_pct") or 0.0,
                n=ev.get("comparison_group_size", 0),
                threshold_pp=ev.get("threshold_pp_above_baseline", 0.0),
                deleted_count=ev.get("area_deleted_count", 0),
                added_count=ev.get("area_added_count", 0),
                previous_count=ev.get("area_previous_count", 0),
                current_count=ev.get("area_current_count", 0),
            )
        except (KeyError, ValueError):
            text = finding.description
    else:
        text = finding.description

    # Always append the disclaimer
    disclaimer = cfg.EXPLANATION_TEMPLATES["DISCLAIMER"][lang]
    return f"{text}\n\n{disclaimer}"


def get_explanation_for_question(
    question_key: str,
    finding: Finding,
    language: str = "simple",
) -> str:
    """
    Return a template-based answer to a common reviewer question.

    question_key options:
        "why_flagged", "what_evidence", "what_percentage",
        "what_verify", "does_prove_wrongdoing"
    """
    lang = language if language in ("technical", "simple", "hindi") else "simple"
    ev = finding.supporting_evidence

    responses: dict[str, dict[str, str]] = {
        "why_flagged": {
            "technical": (
                f"Rule {finding.rule_id} ({finding.title}) was triggered because the computed rate "
                f"({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%) "
                f"exceeded the comparison baseline by more than the configured threshold. "
                f"Review next step: {finding.recommended_next_step or 'Verify source registration records.'}"
            ),
            "simple": (
                f"Rule {finding.rule_id} flagged this area because the rate of change "
                f"({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%) was unusually high "
                f"compared to other areas. This is a statistical signal for human audit, not proof of wrongdoing. "
                f"Recommended step: {finding.recommended_next_step or 'Check the source registration records.'}"
            ),
            "hindi": (
                f"नियम {finding.rule_id} ने इस क्षेत्र को इसलिए चिह्नित किया क्योंकि परिवर्तन दर "
                f"({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%) "
                f"अन्य क्षेत्रों की तुलना में बहुत अधिक थी। यह किसी गलत काम का प्रमाण नहीं है, "
                f"बल्कि मानवीय समीक्षा के लिए एक संकेत है। अनुशंसित कदम: मूल दस्तावेजों की जाँच करें।"
            ),
        },
        "what_evidence": {
            "technical": (
                f"Rule {finding.rule_id} supporting evidence: {ev}. Affected records: {finding.affected_record_count}."
            ),
            "simple": (
                f"Rule {finding.rule_id} evidence: {ev.get('area_deleted_count') or ev.get('area_added_count', finding.affected_record_count)} "
                f"records changed out of {ev.get('area_previous_count') or ev.get('area_current_count', 'N/A')} total in this area."
            ),
            "hindi": (
                f"नियम {finding.rule_id} साक्ष्य: इस क्षेत्र में कुल {ev.get('area_previous_count') or ev.get('area_current_count', 'N/A')} "
                f"में से {ev.get('area_deleted_count') or ev.get('area_added_count', finding.affected_record_count)} रिकॉर्ड बदले।"
            ),
        },
        "what_percentage": {
            "technical": (
                f"Rule {finding.rule_id}: The percentage represents the proportion of records that changed "
                f"relative to the total records in this area ({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%). "
                "This serves as an objective metric against the comparison baseline."
            ),
            "simple": (
                f"Rule {finding.rule_id}: The percentage ({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%) "
                "tells you how many records changed out of all records in this area. "
                "This statistical comparison helps reviewers prioritize verification."
            ),
            "hindi": (
                f"नियम {finding.rule_id}: प्रतिशत ({ev.get('area_removal_rate_pct') or ev.get('area_addition_rate_pct', 'N/A')}%) "
                "यह दर्शाता है कि उस क्षेत्र में कुल रिकॉर्ड के अनुपात में कितने रिकॉर्ड बदले।"
            ),
        },
        "what_verify": {
            "technical": finding.recommended_next_step or (
                "Review original source registration documents to independently verify flagged records."
            ),
            "simple": (
                "A reviewer should check the original source documents to confirm "
                "whether the changes were legitimate and properly authorised."
            ),
            "hindi": (
                "एक समीक्षक को मूल स्रोत दस्तावेजों की जाँच करनी चाहिए "
                "यह पुष्टि करने के लिए कि परिवर्तन वैध थे।"
            ),
        },
        "does_prove_wrongdoing": {
            "technical": cfg.EXPLANATION_TEMPLATES["DISCLAIMER"]["technical"],
            "simple": cfg.EXPLANATION_TEMPLATES["DISCLAIMER"]["simple"],
            "hindi": cfg.EXPLANATION_TEMPLATES["DISCLAIMER"]["hindi"],
        },
    }

    if question_key not in responses:
        refusals = {
            "technical": (
                "I cannot answer that from this evidence. The statistical analysis engine evaluates "
                "aggregate data patterns and data-quality rules; it does not identify individuals, attribute intent, "
                "or prove wrongdoing."
            ),
            "simple": (
                "I cannot answer that from this evidence; the analysis does not identify a person or prove wrongdoing."
            ),
            "hindi": (
                "मैं इस साक्ष्य से इसका उत्तर नहीं दे सकता; यह विश्लेषण किसी व्यक्ति की पहचान नहीं करता है और न ही किसी गलत काम को साबित करता है।"
            ),
        }
        return refusals.get(lang, refusals["simple"])

    return responses[question_key].get(
        lang, responses[question_key].get("simple", "")
    )


def answer_question(
    finding: Finding,
    question_key: str = "why_flagged",
    language: str = "simple",
) -> str:
    """
    Convenience alias for get_explanation_for_question.
    """
    return get_explanation_for_question(
        question_key=question_key,
        finding=finding,
        language=language,
    )


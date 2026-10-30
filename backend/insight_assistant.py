"""
insight_assistant.py — VoterLens AI
=====================================
Hybrid Insight Assistant combining deterministic bilingual summaries
with optional AI-powered conversational follow-up.

Architecture layers:
  Layer 1 — Analysis engine (comparator/detector): unchanged, source of truth.
  Layer 2 — Deterministic explanation engine (this module): bilingual templates.
  Layer 3 — AI conversational engine (this module): configurable provider (Gemini / fallback).
  Layer 4 — Response validation (this module): guards against hallucination and false fraud claims.

Critical rules:
  - Never invent counts, records, calculations, or evidence.
  - Never declare electoral fraud based solely on anomalies.
  - Deterministic summaries must work without an AI API key.
  - All AI calls are backend-only; secrets never reach the frontend.
  - Dataset field values are untrusted; sanitize before including in prompts.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Optional

import config as cfg
from models import StoredAnalysis, Finding, AreaStat

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AI_PROVIDER = os.environ.get("AI_PROVIDER", getattr(cfg, "DEFAULT_AI_PROVIDER", "none")).lower()
AI_MODEL = os.environ.get("AI_MODEL", getattr(cfg, "DEFAULT_AI_MODEL", "gemini-3.8-flash"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", str(getattr(cfg, "DEFAULT_AI_MAX_TOKENS", 1024))))
AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", str(getattr(cfg, "DEFAULT_AI_TIMEOUT_SECONDS", 30))))
MAX_QUESTION_LENGTH = getattr(cfg, "MAX_QUESTION_LENGTH", 500)
SUPPORTED_LANGUAGES = getattr(cfg, "SUPPORTED_LANGUAGES", {"en", "hi"})


def get_ai_config() -> tuple[str, str, str, int, int]:
    """Retrieve active AI provider configuration from globals, env, or cfg."""
    mod = globals()
    provider = str(mod.get("AI_PROVIDER") or os.environ.get("AI_PROVIDER", getattr(cfg, "DEFAULT_AI_PROVIDER", "none"))).lower()
    model = str(mod.get("AI_MODEL") or os.environ.get("AI_MODEL", getattr(cfg, "DEFAULT_AI_MODEL", "gemini-3.8-flash")))
    api_key = str(mod.get("GEMINI_API_KEY") if mod.get("GEMINI_API_KEY") is not None else os.environ.get("GEMINI_API_KEY", ""))
    max_tokens = int(mod.get("AI_MAX_TOKENS") or os.environ.get("AI_MAX_TOKENS", str(getattr(cfg, "DEFAULT_AI_MAX_TOKENS", 1024))))
    timeout = int(mod.get("AI_TIMEOUT_SECONDS") or os.environ.get("AI_TIMEOUT_SECONDS", str(getattr(cfg, "DEFAULT_AI_TIMEOUT_SECONDS", 30))))
    return provider, model, api_key, max_tokens, timeout

# ---------------------------------------------------------------------------
# Prompt injection guard
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(previous|above|all)\s+instructions?"
    r"|you\s+are\s+now"
    r"|system\s*:\s*"
    r"|<\s*/?\s*(?:script|system|prompt))",
    re.IGNORECASE,
)


def _sanitize(text: str, max_len: int = 500) -> str:
    """Sanitize user input or dataset values for safe inclusion in prompts."""
    if not text:
        return ""
    cleaned = _INJECTION_PATTERNS.sub("[FILTERED]", text)
    cleaned = cleaned.replace("```", "'''")
    return cleaned[:max_len].strip()


# ---------------------------------------------------------------------------
# Standard Disclaimers
# ---------------------------------------------------------------------------

DISCLAIMERS = {
    "en": (
        "Statistical signals and anomalies identify patterns for human review. "
        "They do not constitute evidence of electoral fraud or wrongdoing. "
        "Independent verification against physical or official records is required."
    ),
    "hi": (
        "यह सांख्यिकीय निष्कर्ष और विसंगतियां केवल मानवीय समीक्षा के लिए संकेत हैं। "
        "यह किसी भी प्रकार की चुनावी धांधली या गलत काम का प्रमाण नहीं हैं। "
        "मूल आधिकारिक अभिलेखों के साथ स्वतंत्र सत्यापन आवश्यक है।"
    ),
}

SUGGESTED_QUESTIONS = {
    "en": [
        "What are the key findings from this audit?",
        "Which areas have unusual removal or addition rates?",
        "Are these flagged anomalies proof of fraud?",
        "What should an auditor verify first?",
        "Explain the reconciliation numbers for this roll.",
    ],
    "hi": [
        "इस ऑडिट के मुख्य निष्कर्ष क्या हैं?",
        "किन क्षेत्रों में मतदाताओं को हटाने या जोड़ने की दर असामान्य है?",
        "क्या ये विसंगतियां धांधली या धोखाधड़ी का सबूत हैं?",
        "समीक्षक को सबसे पहले किन बातों की पुष्टि करनी चाहिए?",
        "इस सूची के पुनर्मिलन (Reconciliation) आंकड़ों को समझाइए।",
    ],
}


# ---------------------------------------------------------------------------
# Layer 2 — Deterministic Bilingual Summaries
# ---------------------------------------------------------------------------

def generate_summary(stored: StoredAnalysis, language: str = "en") -> dict[str, Any]:
    """
    Generate an executive summary purely from deterministic analysis data.
    Works completely offline without requiring any AI API keys.
    """
    lang = language.lower() if language in SUPPORTED_LANGUAGES else "en"
    comp = stored.comparison_result
    summary_counts = comp.summary
    findings = stored.findings or []
    area_stats = getattr(comp, "area_stats", []) or []

    prev_tot = summary_counts.previous_records
    curr_tot = summary_counts.current_records
    added = summary_counts.added
    deleted = summary_counts.deleted
    modified = summary_counts.modified
    unchanged = summary_counts.unchanged
    ambig_prev = summary_counts.ambiguous_previous
    ambig_curr = summary_counts.ambiguous_current
    net_change = curr_tot - prev_tot

    # Collect flagged areas
    flagged_areas = []
    for stat in area_stats:
        if getattr(stat, "flagged_removal", False) or getattr(stat, "flagged_addition", False):
            flagged_areas.append({
                "area_id": stat.area_id,
                "area_name": stat.area_name,
                "removal_rate": stat.removal_rate_pct,
                "addition_rate": stat.addition_rate_pct,
                "baseline_removal": stat.baseline_removal_rate_pct,
                "rate": stat.removal_rate_pct if stat.flagged_removal else stat.addition_rate_pct,
                "type": "removal" if stat.flagged_removal else "addition",
            })
        elif stat.removal_rate_diff_from_baseline_pct and stat.removal_rate_diff_from_baseline_pct > 0:
            if any((getattr(f, "affected_area_id", None) or getattr(f, "area_id", None)) == stat.area_id for f in findings):
                flagged_areas.append({
                    "area_id": stat.area_id,
                    "area_name": stat.area_name,
                    "removal_rate": stat.removal_rate_pct,
                    "addition_rate": stat.addition_rate_pct,
                    "rate": stat.removal_rate_pct,
                    "type": "removal",
                })

    # Collect evidence references
    evidence_references = []
    for f in findings:
        area_label = getattr(f, "affected_area_name", None) or getattr(f, "affected_area_id", None) or getattr(f, "area_name", None) or getattr(f, "area_id", None) or "General"
        evidence_references.append({
            "type": "finding",
            "id": f.finding_id,
            "label": f"{getattr(f, 'rule_name', f.rule_id)} in {area_label}",
            "priority": f.review_priority,
        })
    for fa in flagged_areas:
        evidence_references.append({
            "type": "area",
            "id": fa["area_id"],
            "label": f"Area {fa['area_id']} ({fa['area_name']})",
        })

    # High priority findings
    high_findings = [f for f in findings if f.review_priority == "HIGH"]
    data_quality_findings = [f for f in findings if f.category == "DATA_QUALITY"]

    if lang == "hi":
        paragraphs = [
            f"**मतदाता सूची विश्लेषण सारांश (विश्लेषण ID: {stored.analysis_id})**",
            (
                f"इस तुलना में कुल **{prev_tot:,}** पिछले रिकॉर्ड और **{curr_tot:,}** वर्तमान रिकॉर्ड का विश्लेषण किया गया। "
                f"कुल मिलाकर **{added:,}** नए रिकॉर्ड जोड़े गए, **{deleted:,}** रिकॉर्ड हटाए गए, "
                f"**{modified:,}** रिकॉर्ड में बदलाव पाया गया, तथा **{unchanged:,}** रिकॉर्ड पूरी तरह अपरिवर्तित रहे। "
                f"शुद्ध परिवर्तन (Net Change) {net_change:+,} रिकॉर्ड का रहा।"
            ),
        ]

        if ambig_prev > 0 or ambig_curr > 0:
            paragraphs.append(
                f"डेटा गुणवत्ता चेतावनी: कुल **{ambig_prev + ambig_curr}** रिकॉर्ड डुप्लिकेट या रिक्त ID के कारण अस्पष्ट (Ambiguous) श्रेणी में रखे गए।"
            )

        if flagged_areas:
            area_names = ", ".join([f"{a['area_name']} ({a['area_id']})" for a in flagged_areas[:3]])
            paragraphs.append(
                f"**प्राथमिकता समीक्षा क्षेत्र:** {len(flagged_areas)} क्षेत्रों में सामान्य आधार रेखा (Baseline) से अधिक परिवर्तन दर दर्ज की गई, "
                f"विशेष रूप से: {area_names}।"
            )

        if high_findings:
            paragraphs.append(
                f"ऑडिट में **{len(high_findings)}** उच्च-प्राथमिकता निष्कर्ष और **{len(data_quality_findings)}** डेटा गुणवत्ता समस्याएं चिह्नित की गई हैं।"
            )

        paragraphs.append(
            f"**समीक्षा दिशानिर्देश:** {DISCLAIMERS['hi']}"
        )
    else:
        paragraphs = [
            f"**Electoral Roll Audit Summary (Analysis ID: {stored.analysis_id})**",
            (
                f"A comparison between **{prev_tot:,}** baseline records and **{curr_tot:,}** current records was completed. "
                f"The audit classified **{added:,}** added records, **{deleted:,}** deleted records, "
                f"**{modified:,}** modified records, and **{unchanged:,}** unchanged records. "
                f"The overall net change is {net_change:+,} records."
            ),
        ]

        if ambig_prev > 0 or ambig_curr > 0:
            paragraphs.append(
                f"Data Quality Flag: **{ambig_prev + ambig_curr}** records were classified as Ambiguous due to duplicate or missing record IDs."
            )

        if flagged_areas:
            area_desc = "; ".join([
                f"{a['area_name']} ({a['area_id']}) with {a.get('rate', 0):.1f}% {a.get('type', 'removal')} rate"
                for a in flagged_areas[:3]
            ])
            paragraphs.append(
                f"**Flagged Areas for Priority Review:** {len(flagged_areas)} area(s) exhibited statistically elevated change rates: {area_desc}."
            )

        if high_findings:
            paragraphs.append(
                f"The engine flagged **{len(high_findings)}** HIGH priority review findings and **{len(data_quality_findings)}** data quality issues."
            )

        paragraphs.append(
            f"**Audit Guidance:** {DISCLAIMERS['en']}"
        )

    summary_text = "\n\n".join(paragraphs)

    return {
        "status": "success",
        "analysis_id": stored.analysis_id,
        "language": lang,
        "source": "deterministic",
        "summary": summary_text,
        "disclaimer": DISCLAIMERS[lang],
        "key_metrics": {
            "previous_total": prev_tot,
            "current_total": curr_tot,
            "added": added,
            "deleted": deleted,
            "modified": modified,
            "unchanged": unchanged,
            "net_change": net_change,
            "flagged_areas_count": len(flagged_areas),
            "findings_count": len(findings),
            "high_priority_findings": len(high_findings),
        },
        "flagged_areas": flagged_areas,
        "evidence_references": evidence_references[:10],
        "suggested_questions": SUGGESTED_QUESTIONS[lang],
    }


# ---------------------------------------------------------------------------
# Layer 3 & 4 — Conversational Follow-up with AI / Fallback
# ---------------------------------------------------------------------------

def _build_factual_context(stored: StoredAnalysis) -> dict[str, Any]:
    """Extract verifiable facts from StoredAnalysis for prompt grounding."""
    comp = stored.comparison_result
    summary_counts = comp.summary
    findings = stored.findings or []
    area_stats = getattr(comp, "area_stats", []) or []

    flagged_areas = []
    for stat in area_stats:
        if (getattr(stat, "flagged_removal", False) or getattr(stat, "flagged_addition", False)
                or (stat.removal_rate_diff_from_baseline_pct and stat.removal_rate_diff_from_baseline_pct > 0)):
            flagged_areas.append({
                "area_id": stat.area_id,
                "area_name": stat.area_name,
                "previous_count": stat.previous_count,
                "current_count": stat.current_count,
                "added_count": stat.added_count,
                "deleted_count": stat.deleted_count,
                "removal_rate_pct": stat.removal_rate_pct,
                "baseline_removal_rate_pct": stat.baseline_removal_rate_pct,
                "diff_from_baseline_pct": stat.removal_rate_diff_from_baseline_pct,
            })

    finding_summaries = []
    for f in findings:
        finding_summaries.append({
            "finding_id": f.finding_id,
            "rule_id": f.rule_id,
            "rule_name": getattr(f, "rule_name", f.rule_id),
            "area_id": getattr(f, "affected_area_id", None) or getattr(f, "area_id", None),
            "area_name": getattr(f, "affected_area_name", None) or getattr(f, "area_name", None),
            "priority": f.review_priority,
            "description": getattr(f, "description", getattr(f, "explanation", "")),
        })

    return {
        "analysis_id": stored.analysis_id,
        "previous_total": summary_counts.previous_records,
        "current_total": summary_counts.current_records,
        "added": summary_counts.added,
        "deleted": summary_counts.deleted,
        "modified": summary_counts.modified,
        "unchanged": summary_counts.unchanged,
        "ambiguous_previous": summary_counts.ambiguous_previous,
        "ambiguous_current": summary_counts.ambiguous_current,
        "flagged_areas": flagged_areas[:8],
        "findings": finding_summaries[:15],
    }


def _deterministic_answer(stored: StoredAnalysis, message: str, language: str) -> str:
    """Fallback generator when AI is disabled, unconfigured, or offline."""
    lang = language.lower() if language in SUPPORTED_LANGUAGES else "en"
    msg = message.lower()
    facts = _build_factual_context(stored)

    # Intent 1: Fraud / wrongdoing allegations
    if any(k in msg for k in ["fraud", "wrongdoing", "crime", "illegal", "cheating", "धांधली", "धोखाधड़ी", "फर्जी"]):
        if lang == "hi":
            return (
                "यह सांख्यिकीय विश्लेषण किसी भी प्रकार की धांधली या गलत काम का प्रमाण नहीं देता है। "
                "पहचाने गए फ्लैग केवल उन क्षेत्रों या रिकॉर्ड्स की ओर ध्यान आकर्षित करते हैं जहां दरें "
                "औसत से अधिक या प्रारूप असामान्य हैं। किसी भी निष्कर्ष पर पहुंचने से पहले भौतिक फॉर्म और "
                "अभिलेखों का मानवीय सत्यापन आवश्यक है।"
            )
        return (
            "This statistical audit cannot establish intent or declare electoral fraud. "
            "The flagged anomalies identify statistical outliers that warrant manual verification "
            "against source documents. Independent administrative inquiry is required before any conclusion."
        )

    # Intent 2: Area / Removals / Additions
    if any(k in msg for k in ["area", "removal", "deleted", "addition", "north valley", "क्षेत्र", "हटाए", "जोड़े"]):
        flagged = facts.get("flagged_areas", [])
        if flagged:
            top = flagged[0]
            if lang == "hi":
                return (
                    f"विश्लेषण के अनुसार, क्षेत्र {top['area_name']} ({top['area_id']}) में हटाने की दर "
                    f"{top.get('removal_rate_pct', 0):.1f}% पाई गई, जो आधारभूत दर ({top.get('baseline_removal_rate_pct', 0):.1f}%) "
                    f"से अधिक है। कुल {top['deleted_count']} रिकॉर्ड हटाए गए और {top['added_count']} रिकॉर्ड जोड़े गए।"
                )
            return (
                f"According to the audit, Area {top['area_name']} ({top['area_id']}) recorded a "
                f"removal rate of {top.get('removal_rate_pct', 0):.1f}%, which is elevated compared "
                f"to the baseline of {top.get('baseline_removal_rate_pct', 0):.1f}%. "
                f"In this area, {top['deleted_count']} records were removed and {top['added_count']} were added."
            )
        else:
            if lang == "hi":
                return "इस विश्लेषण में किसी भी क्षेत्र में असामान्य हटाने या जोड़ने की दर दर्ज नहीं की गई है।"
            return "No area-level change rates significantly exceeded comparison thresholds in this dataset."

    # Intent 3: Verification / reviewer next steps
    if any(k in msg for k in ["verify", "check", "reviewer", "next step", "पुष्टि", "सत्यापन", "जाँच"]):
        if lang == "hi":
            return (
                "समीक्षक के लिए अनुशंसित चरण:\n"
                "1. उच्च-प्राथमिकता वाले क्षेत्रों के लिए फॉर्म 7 (हटाने का अनुरोध) का मिलान करें।\n"
                "2. डुप्लिकेट पहचान संख्या वाले रिकॉर्ड्स के पते और मूल विवरण सत्यापित करें।\n"
                "3. हाल के परिसीमन (Delimitation) या प्रशासनिक सीमा परिवर्तनों की समीक्षा करें।"
            )
        return (
            "Recommended reviewer next steps:\n"
            "1. Audit removal requests (e.g., Form 7) in areas with elevated deletion rates.\n"
            "2. Physically verify demographic details for records flagged with duplicate IDs.\n"
            "3. Cross-reference boundary reorganizations or migration trends that might explain clustering."
        )

    # Intent 4: General summary
    res = generate_summary(stored, language=lang)
    return res["summary"]


def _call_gemini(prompt: str) -> Optional[str]:
    """Call Google Gemini API via official SDK or REST."""
    provider, model_name, api_key, max_tokens, timeout = get_ai_config()
    if not api_key:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key, transport="rest")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.2},
        )
        if response:
            try:
                if response.text:
                    return response.text.strip()
            except (ValueError, AttributeError):
                if getattr(response, "candidates", None):
                    parts = []
                    for cand in response.candidates:
                        if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                            for p in cand.content.parts:
                                if getattr(p, "text", None):
                                    parts.append(p.text)
                    if parts:
                        return "".join(parts).strip()
    except ImportError:
        logger.warning("google-generativeai package not installed; falling back to deterministic response.")
    except Exception as exc:
        logger.error("Gemini API call failed (%s, model=%s): %s", type(exc).__name__, model_name, exc)

    return None


def _is_unsupported_external_answer(answer: str, message: str) -> bool:
    """Reject external answers that assert blame or unsupported wrongdoing."""
    answer_lower = answer.lower()
    question_lower = message.lower()
    asks_for_blame = any(term in question_lower for term in (
        "who committed", "who is responsible", "who did it", "किसने", "कौन दोषी",
    ))
    if asks_for_blame:
        return True

    accusation_patterns = [
        r"\b(?:committed|commit|commits|committing)\s+fraud\b",
        r"\bstole\s+the\s+election\b",
        r"\b(?:is|are|was|were)\s+rigged\b",
        r"\b(?:is|are|was|were)\s+guilty\b",
        r"\b(?:is|are|was|were)\s+(?:a\s+)?criminal\b",
        r"धांधली\s+की",
        r"\bदोषी\s+है\b",
    ]
    for pattern in accusation_patterns:
        match = re.search(pattern, answer_lower)
        if match:
            start = max(0, match.start() - 35)
            prefix = answer_lower[start:match.start()]
            if any(neg in prefix for neg in ("not ", "no ", "never ", "does not ", "cannot ", "without ", "not imply", "प्रमाण नहीं")):
                continue
            return True

    return False


def handle_chat_message(
    stored: StoredAnalysis,
    message: str,
    language: str = "en",
    conversation_id: Optional[str] = None,
    allow_external_ai: bool = False,
) -> dict[str, Any]:
    """
    Handle a user question about the active analysis with hybrid AI + fallback.
    """
    lang = language.lower() if language in SUPPORTED_LANGUAGES else "en"
    clean_message = _sanitize(message, max_len=MAX_QUESTION_LENGTH)
    cid = conversation_id or str(uuid.uuid4())

    facts = _build_factual_context(stored)
    evidence_refs = []
    for f in stored.findings[:5]:
        evidence_refs.append({"type": "finding", "id": f.finding_id, "label": f.title})
    for fa in facts.get("flagged_areas", [])[:3]:
        evidence_refs.append({"type": "area", "id": fa["area_id"], "label": f"{fa['area_name']} ({fa['area_id']})"})

    # Check if AI provider is active
    ai_used = False
    answer_text = None

    provider, model_name, api_key, max_tokens, timeout = get_ai_config()

    if allow_external_ai and provider == "gemini" and api_key:
        facts_json = str(facts)
        system_rules = (
            "You are the VoterLens AI Insight Assistant, an electoral roll transparency expert. "
            "Answer questions strictly using the provided audit facts. "
            "Never invent counts, voter records, or evidence. "
            "Never declare electoral fraud, criminality, or malicious intent; anomalies are statistical signals for human review only. "
            f"Respond concisely in {'Hindi' if lang == 'hi' else 'English'}.\n\n"
            f"AUDIT FACTS:\n{facts_json}\n\n"
            f"USER QUESTION: {clean_message}"
        )
        ai_resp = _call_gemini(system_rules)
        if ai_resp and not _is_unsupported_external_answer(ai_resp, clean_message):
            answer_text = ai_resp
            ai_used = True

    # If AI wasn't used or failed, use deterministic fallback
    if not answer_text:
        answer_text = _deterministic_answer(stored, clean_message, lang)

    # Response validation & disclaimer guarantee
    disclaimer = DISCLAIMERS[lang]
    if "not prove" not in answer_text.lower() and "प्रमाण नहीं" not in answer_text:
        answer_text += f"\n\n*Note: {disclaimer}*"

    return {
        "status": "success",
        "answer": answer_text,
        "language": lang,
        "source": "ai_gemini" if ai_used else "deterministic_fallback",
        "conversation_id": cid,
        "disclaimer": disclaimer,
        "evidence_references": evidence_refs,
        "suggested_questions": SUGGESTED_QUESTIONS[lang],
    }

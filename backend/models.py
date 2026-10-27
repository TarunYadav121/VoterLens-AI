"""
models.py — VoterLens AI
========================
All Pydantic v2 data models used across the backend.

These models define the canonical shapes of:
  - Validation results
  - Comparison results
  - Field-level diffs
  - Findings
  - Evidence Passports
  - Area statistics
  - API responses

No business logic lives here — only data structure definitions.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Validation models
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    """A single validation issue attached to a file or a row."""

    type: str                        # e.g. "MISSING_RECORD_ID"
    severity: str                    # "ERROR" | "WARNING" | "REVIEW_FLAG"
    rule_id: str                     # e.g. "RULE-V-001"
    message: str
    row_index: Optional[int] = None  # 0-based data row index (None = file-level)
    column: Optional[str] = None
    value: Optional[str] = None
    threshold: Optional[Any] = None


class ValidationResult(BaseModel):
    """Aggregated result of validating one CSV file."""

    file_label: str                     # "previous_file" | "current_file"
    row_count: int
    valid_row_count: int
    has_blocking_errors: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    review_flags: list[ValidationIssue] = Field(default_factory=list)
    # row indices that are ambiguous due to duplicate/null record_id
    ambiguous_row_indices: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Comparison models
# ---------------------------------------------------------------------------

class FieldDiff(BaseModel):
    """A single field that changed between the two versions of a record."""

    field: str
    previous_value: Optional[str] = None
    current_value: Optional[str] = None


class AddedRecord(BaseModel):
    """A record that appears only in the current dataset."""

    record_id: str
    change_category: str = "ADDED"
    data: dict[str, Any]


class DeletedRecord(BaseModel):
    """A record that appears only in the previous dataset."""

    record_id: str
    change_category: str = "DELETED"
    data: dict[str, Any]


class ModifiedRecord(BaseModel):
    """A record that exists in both datasets with at least one changed comparison field."""

    record_id: str
    change_category: str = "MODIFIED"
    previous_values: dict[str, Any]
    current_values: dict[str, Any]
    changed_fields: list[str]
    diffs: list[FieldDiff]


class UnchangedRecord(BaseModel):
    """A record that exists in both datasets with identical comparison fields."""

    record_id: str
    change_category: str = "UNCHANGED"
    data: dict[str, Any]


class AmbiguousRecord(BaseModel):
    """A row that cannot be reliably matched due to null or duplicate record_id."""

    record_id: Optional[str]
    change_category: str = "AMBIGUOUS"
    source_file: str                  # "previous" | "current"
    row_index: int                    # 0-based data row index
    reason: str                       # human-readable explanation


# ---------------------------------------------------------------------------
# Area statistics model
# ---------------------------------------------------------------------------

class AreaStat(BaseModel):
    """Aggregate change statistics for a single area_id."""

    area_id: str
    area_name: str
    area_type: Optional[str] = None
    population_group: Optional[str] = None
    administrative_category: Optional[str] = None

    previous_count: int
    current_count: int
    added_count: int
    deleted_count: int
    modified_count: int
    unchanged_count: int
    net_change: int

    # Rates expressed as percentages (0–100); None when denominator is zero
    removal_rate_pct: Optional[float] = None
    addition_rate_pct: Optional[float] = None

    # Baseline comparison (populated by detector)
    baseline_removal_rate_pct: Optional[float] = None
    baseline_addition_rate_pct: Optional[float] = None
    baseline_method: str = "mean_of_all_areas"
    comparison_group_size: int = 0

    removal_rate_diff_from_baseline_pct: Optional[float] = None
    addition_rate_diff_from_baseline_pct: Optional[float] = None

    flagged_removal: bool = False
    flagged_addition: bool = False
    finding_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Comparison result
# ---------------------------------------------------------------------------

class ComparisonSummary(BaseModel):
    """Top-level counts returned in the analysis summary block."""

    previous_records: int
    current_records: int
    added: int
    deleted: int
    modified: int
    unchanged: int
    ambiguous_previous: int
    ambiguous_current: int


class PaginatedRecords(BaseModel):
    """Paginated wrapper for a list of records."""

    total: int
    page: int
    page_size: int
    total_pages: int
    records: list[Any]


class ChangesBlock(BaseModel):
    """All record-change lists returned by the API."""

    added_records: PaginatedRecords
    deleted_records: PaginatedRecords
    modified_records: PaginatedRecords
    unchanged_total: int                  # Full count; fetch on demand
    ambiguous_matches: list[AmbiguousRecord]


class ComparisonResult(BaseModel):
    """Full output of the comparator module."""

    summary: ComparisonSummary
    added: list[AddedRecord] = Field(default_factory=list)
    deleted: list[DeletedRecord] = Field(default_factory=list)
    modified: list[ModifiedRecord] = Field(default_factory=list)
    unchanged: list[UnchangedRecord] = Field(default_factory=list)
    ambiguous_previous: list[AmbiguousRecord] = Field(default_factory=list)
    ambiguous_current: list[AmbiguousRecord] = Field(default_factory=list)
    area_stats: list[AreaStat] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Finding and Evidence Passport
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """A single structured finding emitted by the detector."""

    finding_id: str                        # e.g. "FND-D-007-B01"
    rule_id: str                           # e.g. "RULE-D-007"
    category: str                          # "DATA_QUALITY" | "AGGREGATE_PATTERN"
    title: str
    description: str                       # Neutral language
    review_priority: str                   # "HIGH" | "MEDIUM" | "LOW"
    affected_record_count: int
    affected_area_id: Optional[str] = None
    affected_area_name: Optional[str] = None
    supporting_evidence: dict[str, Any] = Field(default_factory=dict)
    threshold: Optional[float] = None
    baseline: Optional[float] = None
    baseline_method: Optional[str] = None
    comparison_group_size: Optional[int] = None
    possible_explanations: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""
    limitations: str = ""
    detected_at: str = ""


class EvidencePassport(BaseModel):
    """Self-contained reproducibility record for a single finding."""

    passport_id: str
    finding_id: str
    category: str
    observation: str                         # One-sentence neutral statement
    supporting_evidence: dict[str, Any]
    detection_rule_id: str
    detection_rule_name: str
    threshold: Optional[float] = None
    threshold_units: str = ""
    baseline: Optional[float] = None
    baseline_method: str = ""
    comparison_group_size: int = 0
    calculation_details: dict[str, str] = Field(default_factory=dict)
    dataset_fingerprints: dict[str, str] = Field(default_factory=dict)
    analysis_config: dict[str, Any] = Field(default_factory=dict)
    possible_alternative_explanations: list[str] = Field(default_factory=list)
    limitations: str = ""
    recommended_next_steps: list[str] = Field(default_factory=list)
    generated_at: str = ""
    analysis_id: str = ""


# ---------------------------------------------------------------------------
# Full analysis result (stored in-memory and returned via API)
# ---------------------------------------------------------------------------

class StoredAnalysis(BaseModel):
    """Everything stored in the in-memory analysis store for one analysis run."""

    analysis_id: str
    analyzed_at: str
    dataset_fingerprints: dict[str, str]
    validation_results: dict[str, ValidationResult]
    comparison_result: ComparisonResult
    findings: list[Finding]
    evidence_passports: list[EvidencePassport]
    # Config snapshot used for this analysis (for recheck reproducibility)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ---------------------------------------------------------------------------
# API response wrappers
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


class AnalysisResponse(BaseModel):
    """JSON response for POST /api/analyze."""

    analysis_id: str
    status: str
    analyzed_at: str
    dataset_fingerprints: dict[str, str]
    summary: ComparisonSummary
    changes: ChangesBlock
    findings: list[Finding]
    area_comparison: list[AreaStat]
    evidence_passports: list[EvidencePassport]
    validation_warnings: dict[str, Any]


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RecheckResponse(BaseModel):
    status: str
    original_finding: Optional[Finding]
    recheck_finding: Optional[Finding]
    match: Optional[bool]
    recheck_timestamp: str
    dataset_changed: bool = False
    config_changed: bool = False
    message: Optional[str] = None


class ChallengeScenarioResult(BaseModel):
    scenario_id: str
    description: str
    expected: str      # "POSITIVE" | "NEGATIVE"
    predicted: str     # "POSITIVE" | "NEGATIVE"
    outcome: str       # "TRUE_POSITIVE" | "TRUE_NEGATIVE" | "FALSE_POSITIVE" | "FALSE_NEGATIVE"
    finding_id: Optional[str] = None
    notes: str = ""


class ChallengeResponse(BaseModel):
    status: str
    total_scenarios: int
    passed: int
    failed: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: Optional[float]
    recall: Optional[float]
    precision_note: Optional[str] = None
    recall_note: Optional[str] = None
    scenario_results: list[ChallengeScenarioResult]
    disclaimer: str


class CounterfactualResponse(BaseModel):
    area_id: str
    area_name: str
    removal_rate_pct: Optional[float]
    original_comparison: dict[str, Any]
    new_comparison: dict[str, Any]
    status_changed: bool
    explanation: str
    warnings: list[str] = Field(default_factory=list)

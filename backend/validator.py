"""
validator.py — VoterLens AI
============================
CSV validation engine.

Validates a CSV file and returns a ValidationResult containing:
  - errors       (severity="ERROR")      — block analysis
  - warnings     (severity="WARNING")    — analysis continues with limitations
  - review_flags (severity="REVIEW_FLAG") — rows need human verification

No business logic beyond validation lives here.
"""

from __future__ import annotations

import io
import re
from typing import Union

import pandas as pd

import config as cfg
from models import ValidationIssue, ValidationResult

# ISO 8601 date pattern
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _issue(
    severity: str,
    issue_type: str,
    rule_id: str,
    message: str,
    row_index: int | None = None,
    column: str | None = None,
    value: str | None = None,
    threshold=None,
) -> ValidationIssue:
    return ValidationIssue(
        type=issue_type,
        severity=severity,
        rule_id=rule_id,
        message=message,
        row_index=row_index,
        column=column,
        value=str(value) if value is not None else None,
        threshold=threshold,
    )


def validate_csv(
    file_content: bytes,
    file_label: str,
    filename: str = "",
) -> ValidationResult:
    """
    Validate a CSV file provided as raw bytes.

    Parameters
    ----------
    file_content : bytes
        Raw bytes of the uploaded CSV file.
    file_label : str
        "previous_file" or "current_file" — used in error messages.
    filename : str
        Original filename — used to check extension.

    Returns
    -------
    ValidationResult
        Structured validation result. Check `has_blocking_errors` before
        proceeding with analysis.
    """
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    review_flags: list[ValidationIssue] = []
    ambiguous_row_indices: list[int] = []

    # ------------------------------------------------------------------
    # File-level: size check
    # ------------------------------------------------------------------
    if len(file_content) > cfg.MAX_FILE_SIZE_BYTES:
        errors.append(_issue(
            "ERROR", "FILE_TOO_LARGE", "RULE-V-006",
            f"File '{filename}' exceeds the maximum allowed size of "
            f"{cfg.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        ))
        return ValidationResult(
            file_label=file_label, row_count=0, valid_row_count=0,
            has_blocking_errors=True, errors=errors,
        )

    # ------------------------------------------------------------------
    # File-level: extension check
    # ------------------------------------------------------------------
    if filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in cfg.ALLOWED_EXTENSIONS:
            errors.append(_issue(
                "ERROR", "UNSUPPORTED_EXTENSION", "RULE-V-008",
                f"File '{filename}' has extension '{ext}'. Only .csv files are supported.",
            ))
            return ValidationResult(
                file_label=file_label, row_count=0, valid_row_count=0,
                has_blocking_errors=True, errors=errors,
            )

    # ------------------------------------------------------------------
    # File-level: CSV readability
    # ------------------------------------------------------------------
    try:
        df = pd.read_csv(
            io.BytesIO(file_content),
            dtype=str,           # read everything as strings first
            keep_default_na=False,
            na_values=["", "NA", "N/A", "null", "NULL", "None", "NaN"],
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(_issue(
            "ERROR", "UNREADABLE_CSV", "RULE-V-005",
            f"File cannot be parsed as CSV: {type(exc).__name__}.",
        ))
        return ValidationResult(
            file_label=file_label, row_count=0, valid_row_count=0,
            has_blocking_errors=True, errors=errors,
        )

    # ------------------------------------------------------------------
    # File-level: empty file
    # ------------------------------------------------------------------
    if len(df) == 0:
        errors.append(_issue(
            "ERROR", "EMPTY_FILE", "RULE-V-004",
            "File contains zero data rows after the header.",
        ))
        return ValidationResult(
            file_label=file_label, row_count=0, valid_row_count=0,
            has_blocking_errors=True, errors=errors,
        )

    row_count = len(df)

    # ------------------------------------------------------------------
    # File-level: row count limit
    # ------------------------------------------------------------------
    if row_count > cfg.MAX_ROW_COUNT:
        warnings.append(_issue(
            "WARNING", "ROW_COUNT_EXCEEDED", "RULE-V-007",
            f"File has {row_count} rows, which exceeds the maximum of "
            f"{cfg.MAX_ROW_COUNT}. Only the first {cfg.MAX_ROW_COUNT} rows "
            f"will be analysed.",
        ))
        df = df.head(cfg.MAX_ROW_COUNT)
        row_count = len(df)

    # ------------------------------------------------------------------
    # Column-level: required columns
    # ------------------------------------------------------------------
    actual_columns = set(df.columns.tolist())
    for col in cfg.REQUIRED_COLUMNS:
        if col not in actual_columns:
            errors.append(_issue(
                "ERROR", "MISSING_REQUIRED_COLUMN", "RULE-V-003",
                f"Required column '{col}' is absent from the file.",
                column=col,
            ))

    if errors:
        return ValidationResult(
            file_label=file_label, row_count=row_count, valid_row_count=0,
            has_blocking_errors=True, errors=errors,
        )

    # ------------------------------------------------------------------
    # Column-level: optional columns (warnings only)
    # ------------------------------------------------------------------
    for col in cfg.OPTIONAL_COLUMNS:
        if col not in actual_columns:
            warnings.append(_issue(
                "WARNING", "MISSING_OPTIONAL_COLUMN", "RULE-V-003",
                f"Optional column '{col}' is absent. Features that depend on "
                f"this column will be disabled.",
                column=col,
            ))

    # ------------------------------------------------------------------
    # Column-level: unknown/extra columns (warnings only)
    # ------------------------------------------------------------------
    recognized_columns = set(cfg.ALL_SCHEMA_COLUMNS)
    unknown_columns = actual_columns - recognized_columns
    for col in sorted(unknown_columns):
        warnings.append(_issue(
            "WARNING", "UNKNOWN_COLUMN", "RULE-V-014",
            f"Column '{col}' is not part of the recognized schema. It will be ignored during analysis.",
            column=col,
        ))

    # ------------------------------------------------------------------
    # Row-level: record_id checks
    # ------------------------------------------------------------------
    # Identify null record_ids
    null_id_mask = df["record_id"].isna()
    for idx in df.index[null_id_mask]:
        data_row = int(idx)
        errors.append(_issue(
            "ERROR", "MISSING_RECORD_ID", "RULE-V-001",
            f"record_id is null or empty at data row {data_row + 1} (0-indexed: {data_row}). "
            "This row cannot be matched and will be classified AMBIGUOUS.",
            row_index=data_row,
            column="record_id",
        ))
        if data_row not in ambiguous_row_indices:
            ambiguous_row_indices.append(data_row)

    # Identify duplicate record_ids
    non_null_ids = df.loc[~null_id_mask, "record_id"]
    dup_mask = non_null_ids.duplicated(keep=False)
    dup_ids = set(non_null_ids[dup_mask].tolist())
    if dup_ids:
        dup_rows = df.index[df["record_id"].isin(dup_ids)].tolist()
        errors.append(_issue(
            "ERROR", "DUPLICATE_RECORD_ID", "RULE-V-002",
            f"{len(dup_ids)} record_id value(s) appear more than once in this file. "
            f"Affected IDs: {sorted(dup_ids)[:5]}{'...' if len(dup_ids) > 5 else ''}. "
            "These rows will be classified AMBIGUOUS.",
            column="record_id",
        ))
        for idx in dup_rows:
            if int(idx) not in ambiguous_row_indices:
                ambiguous_row_indices.append(int(idx))

    # ------------------------------------------------------------------
    # Row-level: name
    # ------------------------------------------------------------------
    if "name" in actual_columns:
        name_null_mask = df["name"].isna()
        for idx in df.index[name_null_mask]:
            warnings.append(_issue(
                "WARNING", "MISSING_NAME", "RULE-V-015",
                f"name is null or empty at data row {int(idx) + 1}.",
                row_index=int(idx),
                column="name",
            ))

    # ------------------------------------------------------------------
    # Row-level: area_id
    # ------------------------------------------------------------------
    if "area_id" in actual_columns:
        area_null_mask = df["area_id"].isna()
        for idx in df.index[area_null_mask]:
            warnings.append(_issue(
                "WARNING", "MISSING_AREA_ID", "RULE-V-016",
                f"area_id is null or empty at data row {int(idx) + 1}. "
                "This record will not appear in area statistics.",
                row_index=int(idx),
                column="area_id",
            ))

    # ------------------------------------------------------------------
    # Row-level: age
    # ------------------------------------------------------------------
    if "age" in actual_columns:
        for idx, val in df["age"].items():
            row_num = int(idx) + 1
            if pd.isna(val) or val == "":
                warnings.append(_issue(
                    "WARNING", "MISSING_AGE", "RULE-V-009",
                    f"age is missing at data row {row_num}. "
                    "Age-based checks are skipped for this record.",
                    row_index=int(idx),
                    column="age",
                ))
                continue

            # Attempt numeric conversion
            try:
                age_int = int(float(str(val).strip()))
            except (ValueError, TypeError):
                errors.append(_issue(
                    "ERROR", "INVALID_AGE_TYPE", "RULE-V-010",
                    f"age value '{val}' at data row {row_num} cannot be converted "
                    "to an integer.",
                    row_index=int(idx),
                    column="age",
                    value=val,
                ))
                continue

            # Plausibility range
            if age_int < cfg.AGE_MIN_PLAUSIBLE:
                review_flags.append(_issue(
                    "REVIEW_FLAG", "AGE_OUT_OF_RANGE", "RULE-V-011",
                    f"age value {age_int} at data row {row_num} is below the "
                    f"configured plausible minimum of {cfg.AGE_MIN_PLAUSIBLE}. "
                    "Human verification is recommended.",
                    row_index=int(idx),
                    column="age",
                    value=str(age_int),
                    threshold=cfg.AGE_MIN_PLAUSIBLE,
                ))
            elif age_int > cfg.AGE_MAX_PLAUSIBLE:
                review_flags.append(_issue(
                    "REVIEW_FLAG", "AGE_OUT_OF_RANGE", "RULE-V-011",
                    f"age value {age_int} at data row {row_num} is above the "
                    f"configured plausible maximum of {cfg.AGE_MAX_PLAUSIBLE}. "
                    "Human verification is recommended.",
                    row_index=int(idx),
                    column="age",
                    value=str(age_int),
                    threshold=cfg.AGE_MAX_PLAUSIBLE,
                ))

    # ------------------------------------------------------------------
    # Row-level: gender
    # ------------------------------------------------------------------
    if "gender" in actual_columns:
        for idx, val in df["gender"].items():
            if pd.isna(val):
                continue   # missing gender is not an error
            # Normalize to uppercase for comparison
            normalized = str(val).strip().upper()
            if normalized not in {v.upper() for v in cfg.ALLOWED_GENDER}:
                review_flags.append(_issue(
                    "REVIEW_FLAG", "INVALID_GENDER", "RULE-V-012",
                    f"gender value '{val}' at data row {int(idx) + 1} is not in the "
                    f"allowed set {sorted(cfg.ALLOWED_GENDER - {''})}.",
                    row_index=int(idx),
                    column="gender",
                    value=val,
                ))

    # ------------------------------------------------------------------
    # Row-level: area_type
    # ------------------------------------------------------------------
    if "area_type" in actual_columns:
        for idx, val in df["area_type"].items():
            if pd.isna(val):
                continue
            normalized = str(val).strip().lower()
            if normalized not in cfg.ALLOWED_AREA_TYPE:
                review_flags.append(_issue(
                    "REVIEW_FLAG", "INVALID_AREA_TYPE", "RULE-V-013",
                    f"area_type value '{val}' at data row {int(idx) + 1} is not in "
                    f"the allowed set {sorted(cfg.ALLOWED_AREA_TYPE - {''})}.",
                    row_index=int(idx),
                    column="area_type",
                    value=val,
                ))

    # ------------------------------------------------------------------
    # Row-level: registration_date
    # ------------------------------------------------------------------
    if "registration_date" in actual_columns:
        for idx, val in df["registration_date"].items():
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if val_str and not _DATE_RE.match(val_str):
                review_flags.append(_issue(
                    "REVIEW_FLAG", "INVALID_DATE_FORMAT", "RULE-V-014",
                    f"registration_date value '{val_str}' at data row {int(idx) + 1} "
                    "does not match the expected ISO 8601 format YYYY-MM-DD.",
                    row_index=int(idx),
                    column="registration_date",
                    value=val_str,
                ))

    # Only structural/file-level errors block the analysis entirely.
    # Row-level errors (e.g. duplicate IDs, invalid age types) are captured in errors/ambiguous
    # rows, allowing comparator and detector to audit them rather than crashing the pipeline.
    blocking_error_types = {
        "FILE_TOO_LARGE",
        "UNSUPPORTED_EXTENSION",
        "UNREADABLE_CSV",
        "EMPTY_FILE",
        "MISSING_REQUIRED_COLUMN",
    }
    has_blocking = any(e.type in blocking_error_types for e in errors)

    # Deduplicate ambiguous_row_indices
    ambiguous_row_indices = sorted(set(ambiguous_row_indices))

    return ValidationResult(
        file_label=file_label,
        row_count=row_count,
        valid_row_count=row_count - len(ambiguous_row_indices),
        has_blocking_errors=has_blocking,
        errors=errors,
        warnings=warnings,
        review_flags=review_flags,
        ambiguous_row_indices=ambiguous_row_indices,
    )


def validate_and_load(
    file_content: bytes,
    file_label: str,
    filename: str = "",
) -> tuple[ValidationResult, pd.DataFrame | None]:
    """
    Validate and, if no blocking errors, return the parsed DataFrame.

    Missing optional columns are added as all-null columns so the rest of
    the pipeline can assume their existence.

    Returns
    -------
    (ValidationResult, DataFrame | None)
        DataFrame is None if validation has blocking errors.
    """
    result = validate_csv(file_content, file_label, filename)
    if result.has_blocking_errors:
        return result, None

    df = pd.read_csv(
        io.BytesIO(file_content),
        dtype=str,
        keep_default_na=False,
        na_values=["", "NA", "N/A", "null", "NULL", "None", "NaN"],
    )

    if len(df) > cfg.MAX_ROW_COUNT:
        df = df.head(cfg.MAX_ROW_COUNT)

    # Add missing optional columns as all-NaN
    for col in cfg.OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    return result, df


# Backwards compatibility alias
load_and_validate = validate_and_load

"""
comparator.py — VoterLens AI
==============================
Record comparison engine.

Responsibilities:
  1. Identify ADDED, DELETED, MODIFIED, UNCHANGED, and AMBIGUOUS records.
  2. Calculate field-level diffs for modified records.
  3. Compute per-area aggregate statistics.
  4. Verify count-consistency invariants before returning.

Matching is performed exclusively by record_id. No fuzzy matching.
A record appears in exactly one category.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import config as cfg
from models import (
    AddedRecord,
    AmbiguousRecord,
    AreaStat,
    ChangesBlock,
    ComparisonResult,
    ComparisonSummary,
    DeletedRecord,
    FieldDiff,
    ModifiedRecord,
    PaginatedRecords,
    UnchangedRecord,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _nan_equal(a: Any, b: Any) -> bool:
    """Return True if both values are equal, treating NaN == NaN as equal."""
    a_na = pd.isna(a) if not isinstance(a, (list, dict)) else False
    b_na = pd.isna(b) if not isinstance(b, (list, dict)) else False
    if a_na and b_na:
        return True
    if a_na or b_na:
        return False
    return str(a).strip() == str(b).strip()


def _compute_field_diffs(
    prev_row: pd.Series,
    curr_row: pd.Series,
    fields: list[str],
) -> list[FieldDiff]:
    """Return a FieldDiff for every field that changed between the two rows."""
    diffs: list[FieldDiff] = []
    for field in fields:
        prev_val = prev_row.get(field, pd.NA)
        curr_val = curr_row.get(field, pd.NA)
        if not _nan_equal(prev_val, curr_val):
            diffs.append(FieldDiff(
                field=field,
                previous_value=None if pd.isna(prev_val) else str(prev_val),
                current_value=None if pd.isna(curr_val) else str(curr_val),
            ))
    return diffs


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    """Convert a DataFrame row to a plain dict, replacing NaN with None."""
    return {
        k: (None if pd.isna(v) else v)
        for k, v in row.items()
    }


def _paginate(records: list[Any], page: int = 1, page_size: int = cfg.DEFAULT_PAGE_SIZE) -> PaginatedRecords:
    total = len(records)
    page_size = min(page_size, cfg.MAX_PAGE_SIZE)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    return PaginatedRecords(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        records=[r.model_dump() for r in records[start:end]],
    )


# ---------------------------------------------------------------------------
# Area statistics computation
# ---------------------------------------------------------------------------

def _compute_area_stats(
    prev_clean: pd.DataFrame,
    curr_clean: pd.DataFrame,
    added_ids: set[str],
    deleted_ids: set[str],
    modified_ids: set[str],
    unchanged_ids: set[str],
) -> list[AreaStat]:
    """Compute per-area aggregate counts from clean (unambiguous) DataFrames."""

    # Collect all area_ids present in either dataset
    all_area_ids: set[str] = set()
    if "area_id" in prev_clean.columns:
        all_area_ids |= set(prev_clean["area_id"].dropna().unique())
    if "area_id" in curr_clean.columns:
        all_area_ids |= set(curr_clean["area_id"].dropna().unique())

    area_stats: list[AreaStat] = []

    for area_id in sorted(all_area_ids):
        if not area_id or pd.isna(area_id):
            continue

        # Subset previous and current to this area
        prev_area = prev_clean[prev_clean.get("area_id", pd.Series(dtype=str)) == area_id]
        curr_area = curr_clean[curr_clean.get("area_id", pd.Series(dtype=str)) == area_id]

        prev_ids_area = set(prev_area.index)
        curr_ids_area = set(curr_area.index)

        added_count = len(added_ids & curr_ids_area)
        deleted_count = len(deleted_ids & prev_ids_area)
        modified_count = len(modified_ids & prev_ids_area)
        unchanged_count = len(unchanged_ids & prev_ids_area)

        previous_count = len(prev_ids_area)
        current_count = len(curr_ids_area)
        net_change = current_count - previous_count

        # Rates — guard against zero denominators
        removal_rate_pct = (
            round(deleted_count / previous_count * 100, 2)
            if previous_count > 0 else None
        )
        addition_rate_pct = (
            round(added_count / current_count * 100, 2)
            if current_count > 0 else None
        )

        # Area metadata (take from first matching row in either dataset)
        meta_row = (prev_area.iloc[0] if len(prev_area) > 0 else curr_area.iloc[0])

        area_stats.append(AreaStat(
            area_id=area_id,
            area_name=str(meta_row.get("area_name", area_id) or area_id),
            area_type=(
                str(meta_row.get("area_type", None) or "")
                if not pd.isna(meta_row.get("area_type", pd.NA)) else None
            ),
            population_group=(
                str(meta_row.get("population_group", None) or "")
                if not pd.isna(meta_row.get("population_group", pd.NA)) else None
            ),
            administrative_category=(
                str(meta_row.get("administrative_category", None) or "")
                if not pd.isna(meta_row.get("administrative_category", pd.NA)) else None
            ),
            previous_count=previous_count,
            current_count=current_count,
            added_count=added_count,
            deleted_count=deleted_count,
            modified_count=modified_count,
            unchanged_count=unchanged_count,
            net_change=net_change,
            removal_rate_pct=removal_rate_pct,
            addition_rate_pct=addition_rate_pct,
        ))

    return area_stats


# ---------------------------------------------------------------------------
# Main comparison function
# ---------------------------------------------------------------------------

def compare(
    previous_df: pd.DataFrame,
    current_df: pd.DataFrame,
    ambiguous_prev_indices: list[int] | None = None,
    ambiguous_curr_indices: list[int] | None = None,
    prev_ambiguous_indices: list[int] | None = None,
    curr_ambiguous_indices: list[int] | None = None,
) -> ComparisonResult:
    """
    Compare two electoral roll DataFrames and classify every record.

    Parameters
    ----------
    previous_df : pd.DataFrame
        Previous version of the roll (already loaded and validated).
    current_df : pd.DataFrame
        Current version of the roll.
    ambiguous_prev_indices : list[int] | None
        0-based row indices already flagged as ambiguous by the validator
        (null or duplicate record_ids). If None, re-detected here.
    ambiguous_curr_indices : list[int] | None
        Same for the current file.

    Returns
    -------
    ComparisonResult
        Full comparison with all categories, diffs, and area stats.
    """

    # ---------------------------------------------------------------
    # Step 1 — Identify ambiguous rows
    # ---------------------------------------------------------------
    def _find_ambiguous(df: pd.DataFrame, source: str) -> tuple[pd.DataFrame, pd.DataFrame, list[AmbiguousRecord]]:
        """Split df into (clean_df, ambiguous_rows, AmbiguousRecord list)."""
        ambiguous_records: list[AmbiguousRecord] = []

        # Null record_id rows
        null_mask = df["record_id"].isna()

        # Duplicate record_id rows
        non_null = df.loc[~null_mask, "record_id"]
        dup_ids = set(non_null[non_null.duplicated(keep=False)].tolist())
        dup_mask = df["record_id"].isin(dup_ids)

        ambig_mask = null_mask | dup_mask
        ambig_df = df[ambig_mask]
        clean_df = df[~ambig_mask].copy()

        for idx, row in ambig_df.iterrows():
            rid = None if pd.isna(row["record_id"]) else str(row["record_id"])
            reason = "record_id is null or empty" if pd.isna(row["record_id"]) else \
                     f"record_id '{rid}' appears more than once in the {source} file"
            ambiguous_records.append(AmbiguousRecord(
                record_id=rid,
                source_file=source,
                row_index=int(idx),
                reason=reason,
            ))

        return clean_df, ambig_df, ambiguous_records

    prev_clean, _, ambig_prev_list = _find_ambiguous(previous_df.reset_index(drop=True), "previous")
    curr_clean, _, ambig_curr_list = _find_ambiguous(current_df.reset_index(drop=True), "current")

    # Index by record_id for O(1) lookup
    prev_clean = prev_clean.set_index("record_id")
    curr_clean = curr_clean.set_index("record_id")

    prev_ids: set[str] = set(prev_clean.index)
    curr_ids: set[str] = set(curr_clean.index)

    # ---------------------------------------------------------------
    # Step 2 — Set operations
    # ---------------------------------------------------------------
    added_ids   = curr_ids - prev_ids
    deleted_ids = prev_ids - curr_ids
    shared_ids  = prev_ids & curr_ids

    # ---------------------------------------------------------------
    # Step 3 — Classify shared records (MODIFIED vs UNCHANGED)
    # ---------------------------------------------------------------
    modified: list[ModifiedRecord] = []
    unchanged: list[UnchangedRecord] = []
    modified_ids: set[str] = set()
    unchanged_ids: set[str] = set()

    comparison_fields_present = [
        f for f in cfg.COMPARISON_FIELDS if f in prev_clean.columns or f in curr_clean.columns
    ]

    for rid in sorted(shared_ids):
        prev_row = prev_clean.loc[rid]
        curr_row = curr_clean.loc[rid]

        diffs = _compute_field_diffs(prev_row, curr_row, comparison_fields_present)

        if diffs:
            modified.append(ModifiedRecord(
                record_id=rid,
                previous_values=_row_to_dict(prev_row),
                current_values=_row_to_dict(curr_row),
                changed_fields=[d.field for d in diffs],
                diffs=diffs,
            ))
            modified_ids.add(rid)
        else:
            unchanged.append(UnchangedRecord(
                record_id=rid,
                data=_row_to_dict(curr_row),
            ))
            unchanged_ids.add(rid)

    # ---------------------------------------------------------------
    # Step 4 — Build ADDED and DELETED lists
    # ---------------------------------------------------------------
    added: list[AddedRecord] = [
        AddedRecord(record_id=rid, data=_row_to_dict(curr_clean.loc[rid]))
        for rid in sorted(added_ids)
    ]
    deleted: list[DeletedRecord] = [
        DeletedRecord(record_id=rid, data=_row_to_dict(prev_clean.loc[rid]))
        for rid in sorted(deleted_ids)
    ]

    # ---------------------------------------------------------------
    # Step 5 — Area statistics
    # ---------------------------------------------------------------
    # Re-use integer-indexed DataFrames (before set_index) for area lookup
    prev_for_area = previous_df[~previous_df["record_id"].isin(
        [r.record_id for r in ambig_prev_list]
    )].copy()
    curr_for_area = current_df[~current_df["record_id"].isin(
        [r.record_id for r in ambig_curr_list]
    )].copy()

    # Re-index by record_id for area stat function
    prev_for_area_indexed = prev_for_area.set_index("record_id") if "record_id" in prev_for_area.columns else prev_for_area
    curr_for_area_indexed = curr_for_area.set_index("record_id") if "record_id" in curr_for_area.columns else curr_for_area

    area_stats = _compute_area_stats(
        prev_for_area_indexed,
        curr_for_area_indexed,
        added_ids,
        deleted_ids,
        modified_ids,
        unchanged_ids,
    )

    # ---------------------------------------------------------------
    # Step 6 — Summary and count consistency
    # ---------------------------------------------------------------
    summary = ComparisonSummary(
        previous_records=len(previous_df),
        current_records=len(current_df),
        added=len(added),
        deleted=len(deleted),
        modified=len(modified),
        unchanged=len(unchanged),
        ambiguous_previous=len(ambig_prev_list),
        ambiguous_current=len(ambig_curr_list),
    )

    return ComparisonResult(
        summary=summary,
        added=added,
        deleted=deleted,
        modified=modified,
        unchanged=unchanged,
        ambiguous_previous=ambig_prev_list,
        ambiguous_current=ambig_curr_list,
        area_stats=area_stats,
    )


def verify_count_consistency(result: ComparisonResult) -> list[str]:
    """
    Verify that the summary counts are internally consistent.

    Returns a list of discrepancy messages (empty list means all OK).
    """
    issues = []
    s = result.summary

    expected_prev = s.deleted + s.modified + s.unchanged + s.ambiguous_previous
    if expected_prev != s.previous_records:
        issues.append(
            f"Count inconsistency (previous): "
            f"deleted({s.deleted}) + modified({s.modified}) + unchanged({s.unchanged}) "
            f"+ ambiguous_previous({s.ambiguous_previous}) = {expected_prev} "
            f"≠ previous_records({s.previous_records})"
        )

    expected_curr = s.added + s.modified + s.unchanged + s.ambiguous_current
    if expected_curr != s.current_records:
        issues.append(
            f"Count inconsistency (current): "
            f"added({s.added}) + modified({s.modified}) + unchanged({s.unchanged}) "
            f"+ ambiguous_current({s.ambiguous_current}) = {expected_curr} "
            f"≠ current_records({s.current_records})"
        )

    return issues


def build_changes_block(result: ComparisonResult) -> ChangesBlock:
    """Build the paginated ChangesBlock for the API response."""
    return ChangesBlock(
        added_records=_paginate(result.added),
        deleted_records=_paginate(result.deleted),
        modified_records=_paginate(result.modified),
        unchanged_total=len(result.unchanged),
        ambiguous_matches=result.ambiguous_previous + result.ambiguous_current,
    )

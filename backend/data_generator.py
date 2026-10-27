"""
data_generator.py — VoterLens AI
==================================
Generates deterministic synthetic electoral-roll-style CSV datasets.

Produces:
  data/previous_roll.csv    — previous version of the electoral roll
  data/current_roll.csv     — current version of the electoral roll
  data/expected_outcomes.json — machine-readable expected classifications

All datasets use entirely fictional names and synthetic identifiers.
No real voter data is copied or referenced.

Usage:
    python data_generator.py

A fixed random seed (42) ensures identical output on every run.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pandas as pd

import config as cfg

# ---------------------------------------------------------------------------
# Fictional name pools (entirely synthetic)
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Arjun", "Priya", "Ravi", "Kavya", "Amit", "Sneha", "Raj", "Meera",
    "Vikram", "Anjali", "Suresh", "Pooja", "Anand", "Divya", "Kiran",
    "Nisha", "Deepak", "Rekha", "Manoj", "Sunita", "Rahul", "Geeta",
    "Sanjay", "Lata", "Arun", "Seema", "Prakash", "Uma", "Vinod", "Sita",
    "Ramesh", "Kamla", "Ashok", "Radha", "Mohan", "Savita", "Gopal",
    "Asha", "Naresh", "Parvati", "Harish", "Shanti", "Sunil", "Usha",
    "Rajesh", "Mala", "Dinesh", "Rani", "Ajay", "Sarla",
]

LAST_NAMES = [
    "Mehta", "Sharma", "Kumar", "Nair", "Patel", "Singh", "Gupta", "Rao",
    "Joshi", "Shah", "Verma", "Pandey", "Tiwari", "Mishra", "Yadav",
    "Choudhary", "Srivastava", "Dubey", "Chauhan", "Reddy", "Nayak",
    "Iyer", "Menon", "Pillai", "Bose", "Ghosh", "Das", "Chatterjee",
    "Mukherjee", "Banerjee", "Dey", "Sen", "Roy", "Pal", "Malik",
    "Thakur", "Rathore", "Bisht", "Rawat", "Bhatt",
]

DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _make_id(prefix: str, n: int) -> str:
    return f"{prefix}-{n:04d}"


def _pick_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _pick_age(rng: random.Random, min_age: int = 18, max_age: int = 90) -> int:
    return rng.randint(min_age, max_age)


def _pick_gender(rng: random.Random) -> str:
    return rng.choice(["M", "M", "M", "F", "F", "F", "O", "U"])


def _pick_polling_station(area_id: str, rng: random.Random) -> str:
    station_num = rng.randint(1, 5)
    return f"PS-{area_id}-{station_num:02d}"


def _pick_date(rng: random.Random) -> str:
    year = rng.randint(2010, 2024)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


def _base_row(
    rng: random.Random,
    record_id: str,
    area_id: str,
) -> dict:
    """Generate a complete synthetic record row."""
    return {
        "record_id": record_id,
        "name": _pick_name(rng),
        "age": _pick_age(rng),
        "gender": _pick_gender(rng),
        "area_id": area_id,
        "area_name": cfg.GENERATOR_AREA_NAMES[area_id],
        "area_type": cfg.GENERATOR_AREA_TYPES[area_id],
        "population_group": cfg.GENERATOR_POPULATION_GROUPS[area_id],
        "administrative_category": "ward",
        "polling_station_id": _pick_polling_station(area_id, rng),
        "registration_date": _pick_date(rng),
    }


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_datasets() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Generate previous and current electoral roll DataFrames plus
    the expected-outcome manifest.

    Returns:
        (previous_df, current_df, expected_outcomes)
    """
    rng = random.Random(cfg.GENERATOR_RANDOM_SEED)
    counter = 1
    previous_rows: list[dict] = []
    current_rows: list[dict] = []
    expected: dict[str, str] = {}   # record_id -> expected classification

    # -----------------------------------------------------------------------
    # SCEN-01: 80 unchanged records spread across areas A01 and D01
    # -----------------------------------------------------------------------
    for _ in range(80):
        area_id = rng.choice(["A01", "D01"])
        rid = _make_id("SYN", counter)
        counter += 1
        row = _base_row(rng, rid, area_id)
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    # -----------------------------------------------------------------------
    # SCEN-02: 10 added records (present in current only, area C01)
    # The high number creates a detectable HIGH_ADDITION_RATE for C01
    # -----------------------------------------------------------------------
    for _ in range(10):
        rid = _make_id("NEW", counter)
        counter += 1
        row = _base_row(rng, rid, "C01")
        current_rows.append(row.copy())
        expected[rid] = "ADDED"

    # -----------------------------------------------------------------------
    # SCEN-03: 5 deleted records (present in previous only, area A01)
    # -----------------------------------------------------------------------
    for _ in range(5):
        rid = _make_id("DEL", counter)
        counter += 1
        row = _base_row(rng, rid, "A01")
        previous_rows.append(row.copy())
        expected[rid] = "DELETED"

    # -----------------------------------------------------------------------
    # SCEN-04: 8 modified records — single field change (age += 1)
    # -----------------------------------------------------------------------
    for _ in range(8):
        area_id = rng.choice(["A01", "D01"])
        rid = _make_id("MOD", counter)
        counter += 1
        prev_row = _base_row(rng, rid, area_id)
        curr_row = prev_row.copy()
        curr_row["age"] = prev_row["age"] + 1
        previous_rows.append(prev_row)
        current_rows.append(curr_row)
        expected[rid] = "MODIFIED"

    # -----------------------------------------------------------------------
    # SCEN-05: 3 modified records — multiple field changes (age + area transfer)
    # -----------------------------------------------------------------------
    for _ in range(3):
        rid = _make_id("MUL", counter)
        counter += 1
        prev_row = _base_row(rng, rid, "A01")
        curr_row = prev_row.copy()
        curr_row["age"] = prev_row["age"] + 1
        curr_row["area_id"] = "D01"
        curr_row["area_name"] = cfg.GENERATOR_AREA_NAMES["D01"]
        curr_row["area_type"] = cfg.GENERATOR_AREA_TYPES["D01"]
        curr_row["population_group"] = cfg.GENERATOR_POPULATION_GROUPS["D01"]
        curr_row["polling_station_id"] = _pick_polling_station("D01", rng)
        previous_rows.append(prev_row)
        current_rows.append(curr_row)
        expected[rid] = "MODIFIED"

    # -----------------------------------------------------------------------
    # SCEN-06: 4 records with missing age (null) in both versions → UNCHANGED
    # -----------------------------------------------------------------------
    for _ in range(4):
        rid = _make_id("NAG", counter)
        counter += 1
        row = _base_row(rng, rid, "E01")
        row["age"] = None          # missing age
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    # -----------------------------------------------------------------------
    # SCEN-07: 2 records with non-numeric age in both versions → UNCHANGED
    # (validator flags them; comparator still processes them as UNCHANGED)
    # -----------------------------------------------------------------------
    for i, bad_val in enumerate(["thirty", "N/A"]):
        rid = _make_id("IAG", counter)
        counter += 1
        row = _base_row(rng, rid, "E01")
        row["age"] = bad_val       # invalid age — will trigger RULE-V-010
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    # -----------------------------------------------------------------------
    # SCEN-08: 2 rows sharing one record_id in previous → AMBIGUOUS (previous)
    # -----------------------------------------------------------------------
    dup_id_prev = "DUP-PREV-0001"
    for _ in range(2):
        row = _base_row(rng, dup_id_prev, "A01")
        previous_rows.append(row)
    # Do NOT add to expected — ambiguous records are reported separately
    expected[dup_id_prev] = "AMBIGUOUS"

    # -----------------------------------------------------------------------
    # SCEN-09: 2 rows sharing one record_id in current → AMBIGUOUS (current)
    # -----------------------------------------------------------------------
    dup_id_curr = "DUP-CURR-0001"
    for _ in range(2):
        row = _base_row(rng, dup_id_curr, "B01")
        current_rows.append(row)
    expected[dup_id_curr] = "AMBIGUOUS"

    # -----------------------------------------------------------------------
    # SCEN-10: Area B01 — bulk deletions to create HIGH_REMOVAL_RATE
    # Add 200 records to previous for B01, only 123 survive to current.
    # Removal rate ≈ 38.5% (well above 20% threshold)
    # -----------------------------------------------------------------------
    b01_ids = []
    for _ in range(200):
        rid = _make_id("B01", counter)
        counter += 1
        row = _base_row(rng, rid, "B01")
        previous_rows.append(row.copy())
        b01_ids.append((rid, row))

    # Keep 123, delete 77
    rng.shuffle(b01_ids)
    for rid, row in b01_ids[:123]:
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"
    for rid, row in b01_ids[123:]:
        expected[rid] = "DELETED"

    # -----------------------------------------------------------------------
    # SCEN-11: Area C01 — bulk additions to create HIGH_ADDITION_RATE
    # C01 already got 10 added records from SCEN-02.
    # Add 20 more previous records for C01, plus 50 new in current.
    # Removal: 0%, Addition: 50/70 ≈ 71%
    # -----------------------------------------------------------------------
    for _ in range(20):
        rid = _make_id("C01", counter)
        counter += 1
        row = _base_row(rng, rid, "C01")
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    for _ in range(50):
        rid = _make_id("C01N", counter)
        counter += 1
        row = _base_row(rng, rid, "C01")
        current_rows.append(row.copy())
        expected[rid] = "ADDED"

    # -----------------------------------------------------------------------
    # SCEN-12: Area E01 already populated above (clean — SCEN-06/07).
    # Add a few more normal records to ensure it's in area stats.
    # -----------------------------------------------------------------------
    for _ in range(10):
        rid = _make_id("E01", counter)
        counter += 1
        row = _base_row(rng, rid, "E01")
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    # -----------------------------------------------------------------------
    # SCEN-13: 5 rows with missing area_type (present in both) → UNCHANGED
    # -----------------------------------------------------------------------
    for _ in range(5):
        rid = _make_id("NAT", counter)
        counter += 1
        row = _base_row(rng, rid, "D01")
        row["area_type"] = None    # missing area_type
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    # -----------------------------------------------------------------------
    # SCEN-14: 3 rows with invalid gender value → REVIEW_FLAG
    # -----------------------------------------------------------------------
    for bad_gender in ["X", "Z", "Unknown"]:
        rid = _make_id("IGN", counter)
        counter += 1
        row = _base_row(rng, rid, "D01")
        row["gender"] = bad_gender
        previous_rows.append(row.copy())
        current_rows.append(row.copy())
        expected[rid] = "UNCHANGED"

    previous_df = pd.DataFrame(previous_rows, columns=cfg.ALL_SCHEMA_COLUMNS)
    current_df = pd.DataFrame(current_rows, columns=cfg.ALL_SCHEMA_COLUMNS)

    return previous_df, current_df, expected


def generate_clean_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate two identical datasets with no anomalies.
    Used to verify the detector produces zero findings on clean data.
    """
    rng = random.Random(cfg.GENERATOR_RANDOM_SEED + 1)
    rows: list[dict] = []
    counter = 1

    area_ids = list(cfg.GENERATOR_AREA_IDS)
    records_per_area = 20

    for area_id in area_ids:
        for _ in range(records_per_area):
            rid = _make_id("CLN", counter)
            counter += 1
            rows.append(_base_row(rng, rid, area_id))

    df = pd.DataFrame(rows, columns=cfg.ALL_SCHEMA_COLUMNS)
    return df.copy(), df.copy()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating synthetic datasets with seed 42 ...")
    previous_df, current_df, expected = generate_datasets()

    prev_path = DATA_DIR / "previous_roll.csv"
    curr_path = DATA_DIR / "current_roll.csv"
    exp_path = DATA_DIR / "expected_outcomes.json"

    previous_df.to_csv(prev_path, index=False)
    current_df.to_csv(curr_path, index=False)

    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=2)

    print(f"  previous_roll.csv  : {len(previous_df)} rows -> {prev_path}")
    print(f"  current_roll.csv   : {len(current_df)} rows -> {curr_path}")
    print(f"  expected_outcomes  : {len(expected)} entries -> {exp_path}")

    # Verify scenario counts
    from collections import Counter
    counts = Counter(expected.values())
    print("\nExpected outcome breakdown:")
    for label, count in sorted(counts.items()):
        print(f"  {label:12s}: {count}")

    print("\nDone. Run 'python data_generator.py' again to reproduce identical files.")


if __name__ == "__main__":
    main()

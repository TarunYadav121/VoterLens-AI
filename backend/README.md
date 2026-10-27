# VoterLens AI — Backend Service

A transparent, explainable audit engine and REST API for detecting data-quality anomalies, classification shifts, and aggregate patterns between electoral roll releases.

---

## 🏛️ Architecture Overview

```
VoterLens-AI/backend/
├── app.py                  # Flask application factory, routes & error handlers
├── config.py               # Single source of truth for thresholds, schemas & rules
├── models.py               # Pydantic v2 data models & validation schemas
├── validator.py            # CSV validation engine (16 rules, 3 severity levels)
├── comparator.py           # Record matching, field diffs & area aggregation
├── detector.py             # Deterministic anomaly detection & counterfactual engine
├── explainer.py            # Evidence Passport generator & multilingual explanations
├── reporter.py             # CSV export module (summary, changes, findings, areas)
├── data_generator.py       # Deterministic synthetic dataset generator (seed 42)
├── requirements.txt        # Production & testing dependencies
├── data/                   # Generated sample roll datasets (CSV & JSON)
└── tests/                  # Automated pytest suite (unit, integration & API tests)
    ├── conftest.py
    ├── test_validator.py
    ├── test_comparator.py
    ├── test_detector.py
    ├── test_explainer.py
    ├── test_reporter.py
    └── test_api.py
```

---

## 🚀 Quickstart

### 1. Environment Setup

```bash
cd backend
python -m venv venv

# On Windows (cmd / powershell):
venv\Scripts\activate

# On Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Generate Synthetic Datasets

```bash
python data_generator.py
```
This generates:
- `data/previous_roll.csv`
- `data/current_roll.csv`
- `data/expected_outcomes.json`

### 3. Run the Development Server

```bash
python app.py
```
The API starts locally at `http://localhost:5000`.

### 4. Run the Test Suite

```bash
pytest tests/ -v --tb=short
```

---

## 📡 API Contract

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Service health status & metadata |
| `GET` | `/api/sample-data` | Metadata for previous and current sample datasets |
| `GET` | `/api/sample-data/previous` | Download `previous_roll.csv` |
| `GET` | `/api/sample-data/current` | Download `current_roll.csv` |
| `POST` | `/api/analyze` | Upload two CSV files (`previous_file`, `current_file`) for full comparative audit |
| `POST` | `/api/compare-areas` | Counterfactual Audit Lab — test area with new baseline methods or thresholds |
| `POST` | `/api/recheck-finding` | Recheck and verify a specific finding deterministically |
| `GET` | `/api/export/<analysis_id>/<report_type>` | Download CSV export (`summary`, `added`, `deleted`, `modified`, `findings`, `area_comparison`) |
| `POST` | `/api/challenge/run` | Execute the 10-scenario False-Alarm Challenge with accuracy metrics |
| `GET` | `/api/record/<analysis_id>/<record_id>` | Single record change inspector with field-level diffs |
| `POST` | `/api/explain-qa` | Multilingual Q&A assistant (`simple`, `technical`, `hindi`) |

---

## 🛡️ Responsible AI & Transparency Disclaimer

VoterLens AI uses strictly deterministic rules and verified statistical baselines.
**Findings emitted by this system do not prove or assert fraud or wrongdoing.**
Every finding serves exclusively as an objective, transparent signal to guide human verification and audit.

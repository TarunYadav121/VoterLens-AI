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

For deployment, use a production WSGI server such as Gunicorn, bind only to
the required interface, set `FLASK_DEBUG=0`, configure explicit
`ALLOWED_ORIGINS`, and keep `CORS_ALLOW_ALL=0`. The default host is
`127.0.0.1`; `HOST`, `PORT`, and `FLASK_DEBUG` are environment-configurable.

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
| `POST` | `/api/chat/explain` | Deterministic bilingual analysis summary |
| `POST` | `/api/chat/message` | Evidence-grounded chat; external AI requires `allow_external_ai: true` |

## Prototype limits and privacy

This project is a synthetic-data demonstration. Do not upload real voter
information. Each uploaded CSV is limited to 20 MiB and 100,000 rows. The
backend retains at most 10 analyses and an estimated 100 MiB of uploaded input
bytes in an in-memory LRU; parsed objects can use more memory, and all analyses
are lost on restart. This is not a durable or multi-user authorization layer.

Record-level `added` and `deleted` exports may contain names, ages, gender, and
other uploaded columns. They are suitable only for a controlled local demo.
Authentication, authorization, retention controls, and redaction are required
before public deployment or use with personal data. CSV output prefixes
spreadsheet-formula-like leading characters to reduce formula-injection risk.

The assistant uses deterministic responses by default (`AI_PROVIDER=none`).
Gemini is optional, backend-only, and requires both backend credentials and an
explicit per-request `allow_external_ai` opt-in. The provider receives only
aggregate audit facts, not full record contents. External provider processing
still has residual privacy and response-quality risks.

---

## 🛡️ Responsible AI & Transparency Disclaimer

VoterLens AI uses strictly deterministic rules and verified statistical baselines.
**Findings emitted by this system do not prove or assert fraud or wrongdoing.**
Every finding serves exclusively as an objective, transparent signal to guide human verification and audit.

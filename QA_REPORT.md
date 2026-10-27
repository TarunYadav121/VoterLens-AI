# VoterLens AI QA and Security Report

Date: 2026-10-27  
Environment: macOS, Python 3.9.6, repository `backend/venv`

## 1. Summary

| Area | Result | Notes |
|---|---|---|
| Environment and imports | PASS | Python 3.9.6; dependencies installed successfully; all nine backend modules imported. No virtualenv was active, so the checked-in `backend/venv` was used. |
| Existing backend tests | PASS | 62 passed from both the repository root and `backend/`; both pytest configurations work. |
| QA correctness tests | FAIL | 8 passed and 4 failed. Formatting normalization, sample-data analysis, recheck metadata, and invalid threshold handling failed. |
| Live backend smoke test | PARTIAL | `/api/health`, sample metadata/downloads, clean analysis, all follow-up routes, six exports, and challenge execution worked. Direct `python app.py` could not use port 5000 because macOS AirTunes occupied it; Flask CLI worked on port 5050. |
| Input/error handling | PARTIAL | Most tested errors were structured JSON. A nonnumeric threshold raised an uncaught `ValueError` in Flask testing. Extra columns and invalid age values were accepted rather than rejected. |
| Security/privacy | PARTIAL | No filename path traversal was found and storage is capped, but wildcard CORS and production debug binding are unsafe; analysis IDs are bearer-like access references. |
| Responsible AI | PARTIAL | Findings contain neutral evidence, alternatives, limitations, and next steps, and the explicit wrongdoing answer is safe. Unsupported questions return a menu instead of explicitly saying the evidence cannot answer. Simple/Hindi answers omit much of the required context. |
| Frontend | FAIL | `npm install`, `npm run build`, and `npm run lint` pass from `/frontend`, but `frontend/src/App.jsx` is still the default Vite counter page and does not call the backend. No API base URL/configuration was found. |

## 2. Verified bugs

### Critical

None verified.

### High

1. **Production startup enables Flask debug mode on all interfaces**
   - **File/lines:** [backend/app.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/app.py:901)
   - **Reproduction:** Run `cd backend && ./venv/bin/python app.py`; the code executes `app.run(host="0.0.0.0", port=5000, debug=True)`. Trigger malformed `threshold_override` through `/api/compare-areas`.
   - **Expected:** A production-safe WSGI deployment should not expose the Werkzeug debugger or bind publicly by default.
   - **Actual:** All interfaces are bound and debug is enabled. An uncaught exception can expose the interactive debugger.
   - **Suggested fix:** Use gunicorn for deployment, default to loopback for local development, and make host/port/debug explicit environment configuration with debug disabled unless explicitly local.

2. **Wildcard CORS exposes record and export responses to arbitrary origins**
   - **File/lines:** [backend/app.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/app.py:90)
   - **Reproduction:** Send `Origin: https://attacker.example` to `/api/health`, `/api/record/<analysis_id>/<record_id>`, or `/api/export/<analysis_id>/added`; the response includes `Access-Control-Allow-Origin: *`.
   - **Expected:** Only the trusted frontend origin(s) should be able to read analysis and record responses.
   - **Actual:** Every `/api/*` route allows every origin. The analysis ID is the only lookup secret and there is no authentication/authorization.
   - **Suggested fix:** Restrict CORS by environment and add authentication/authorization or scoped, short-lived analysis access tokens.

### Medium

3. **Formatting-only case/whitespace changes are classified as modified**
   - **File/lines:** [backend/comparator.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/comparator.py:42)
   - **Reproduction:** Compare one record with `name="Alice Smith"` to the same record with `name="  alice   smith  "`. QA test `test_formatting_only_differences_are_unchanged` fails.
   - **Expected:** Extra spaces and upper/lower-case differences are normalized and classified `UNCHANGED`.
   - **Actual:** `_nan_equal` strips outer whitespace but does not collapse internal whitespace or case-fold; the record is `MODIFIED`.
   - **Suggested fix:** Apply field-aware canonicalization before comparison (at minimum trim, collapse whitespace, and case-fold textual comparison fields) while preserving original values in evidence.

4. **Provided planted sample data cannot be analyzed**
   - **File/lines:** [backend/app.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/app.py:229), [backend/validator.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/validator.py:160)
   - **Reproduction:** `curl -X POST http://127.0.0.1:5050/api/analyze -F previous_file=@backend/data/previous_roll.csv -F current_file=@backend/data/current_roll.csv` returns HTTP 400 `VALIDATION_FAILED`. Errors identify duplicate `DUP-PREV-0001` and age `thirty`.
   - **Expected:** The supplied `expected_outcomes.json` sample should be usable to demonstrate planted ambiguous/quality findings.
   - **Actual:** Duplicate IDs and invalid age are blocking errors, so no `analysis_id`, findings, or comparison is returned.
   - **Suggested fix:** Treat intentionally planted quality issues as nonblocking warnings/ambiguous rows when safe, or provide a clean demo sample separate from the deliberately invalid QA sample and update the documented flow.

5. **Nonnumeric threshold causes an uncaught exception**
   - **File/lines:** [backend/app.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/app.py:386)
   - **Reproduction:** First create a valid analysis, then POST `{"analysis_id":"<id>","area_id":"A01","threshold_override":"not-a-number"}` to `/api/compare-areas`. The QA client raises `ValueError: could not convert string to float: 'not-a-number'`; with debug enabled this can become an HTML debugger response.
   - **Expected:** HTTP 400 structured JSON such as `INVALID_THRESHOLD`.
   - **Actual:** `float()` is called without validation/catching.
   - **Suggested fix:** Parse with a narrow `try/except (TypeError, ValueError)`, return `INVALID_THRESHOLD`, and validate the final numeric range once.

6. **Recheck response omits dataset/config change status**
   - **File/lines:** [backend/app.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/app.py:422)
   - **Reproduction:** Analyze a pair that creates a finding, then POST `/api/recheck-finding` with its analysis and finding IDs. The response has `match`, original/recheck findings, and timestamp, but no `dataset_changed` or `config_changed`. QA test `test_recheck_reports_dataset_and_config_change_status` fails.
   - **Expected:** Recheck reports whether dataset fingerprints or the saved config differ from the current values.
   - **Actual:** It only reruns detection against the stored result and reports `match`.
   - **Suggested fix:** Persist/compare current fingerprints and configuration, and add explicit boolean fields plus an explanation to the response model.

7. **Unsupported explain-qa questions are not evidence-grounded refusals**
   - **File/lines:** [backend/explainer.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/explainer.py:374)
   - **Reproduction:** POST `/api/explain-qa` with `question_key="who_committed_fraud"`. The answer is `Question not recognised. Please select from: ...`.
   - **Expected:** The answer should explicitly say the evidence cannot identify a perpetrator or establish wrongdoing.
   - **Actual:** It returns a generic menu and does not directly refuse the unsupported inference.
   - **Suggested fix:** Add an explicit unsupported-question response: “I cannot answer that from this evidence; the analysis does not identify a person or prove wrongdoing.”

8. **Record-level explanation variants omit required context**
   - **File/lines:** [backend/explainer.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/explainer.py:310)
   - **Reproduction:** Request `why_flagged` or `what_percentage` in simple/Hindi. These answers do not include the rule ID, concrete evidence, alternatives, limitations, and next step together.
   - **Expected:** Every generated explanation includes rule, evidence, alternative explanations, limitations, and next step.
   - **Actual:** The structured finding/evidence passport has those fields, but several rendered answers are short generic text.
   - **Suggested fix:** Render a consistent evidence-grounded explanation envelope for every language/question, including a neutral disclaimer and review next step.

### Low

9. **Unknown columns and out-of-range ages are accepted without a blocking API warning**
   - **Files/lines:** [backend/validator.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/validator.py:175)
   - **Reproduction:** Upload valid CSVs with an `extra` column, age `-2`, or age `999999999`; all returned HTTP 200 in the probe. Validation warnings should be inspected by callers, but the schema and age constraints are not enforced as errors.
   - **Expected:** Unknown columns and invalid age ranges should be clearly rejected or consistently surfaced as structured review flags.
   - **Actual:** The analysis succeeds and can treat these rows as ordinary data.
   - **Suggested fix:** Define an explicit unknown-column policy and enforce configured minimum/maximum age bounds as review flags or blocking errors.

## 3. Tests and coverage

Commands actually run:

- `./backend/venv/bin/python -m pip install -r backend/requirements.txt`: passed.
- Root: `./backend/venv/bin/python -m pytest --cov=backend --cov-report=term-missing`: 62 passed, 84% coverage.
- Backend: `cd backend && ./venv/bin/python -m pytest --cov=. --cov-report=term-missing`: 62 passed, 84% coverage.
- With QA tests: `./backend/venv/bin/python -m pytest --cov=backend --cov-report=term-missing`: 70 passed, 4 failed, 85% total coverage.

Lowest module coverage in the full run including QA:

| Module | Coverage |
|---|---:|
| `backend/data_generator.py` | 23% |
| `backend/app.py` | 80% |
| `backend/explainer.py` | 82% |
| `backend/validator.py` | 87% |

The added tests are in [backend/tests/qa/test_qa_correctness.py](/Users/yuvraj/Documents/GitHub/VoterLens-AI/backend/tests/qa/test_qa_correctness.py). They verify summary invariants, exact hand-made comparison, area rates, formatting normalization, sample outcomes, recheck metadata, insufficient comparison groups, malformed CSVs, duplicate IDs, and invalid threshold handling.

## 4. Live endpoint status

Verified on `http://127.0.0.1:5050`:

- PASS: health, sample metadata, previous/current sample downloads.
- PASS: valid multipart analysis using a hand-made pair.
- PASS: `compare-areas` with `all_areas` and `similar_areas`; insufficient similar-area groups return a warning.
- PASS: recheck execution and matching (metadata contract remains incomplete).
- PASS: record lookup.
- PASS: exports `summary`, `added`, `deleted`, `modified`, `findings`, and `area_comparison`.
- PASS: challenge run: 10 scenarios, 10 passed, precision 1.0, recall 1.0.
- PASS: missing files, wrong extension, malformed JSON body, unknown analysis, unknown record, and file-too-large cases returned JSON.
- PARTIAL/FAIL: sample analysis, nonnumeric threshold, all-added/all-deleted empty-side scenarios, and formatting normalization.

The six successful export types include record fields such as names in added/deleted CSVs. This is acceptable for a trusted local demo only; it is a privacy concern for shared deployment.

## 5. Gaps and untested specification areas

- The frontend is not wired to any backend endpoint; end-to-end browser upload and results rendering are therefore missing.
- No authentication, authorization, tenant isolation, or analysis-ID access control exists.
- There is no persistence or cleanup policy beyond process lifetime/LRU eviction; uploads are not written to disk, but stored analysis objects remain in memory until eviction or process termination.
- The QA matrix does not yet cover every permutation of binary/encoding/BOM inputs through a committed regression assertion, although live probes were run for each.
- The API does not expose a documented way to retrieve all unchanged records beyond pagination fields.
- Production deployment configuration and a reverse proxy/TLS policy are absent.
- Sample planted data and the expected-outcomes contract are inconsistent with the blocking validator behavior.

## 6. Final verdict

**Not ready for a hackathon demo as an end-to-end product.** The backend’s core comparison and challenge paths work, and the existing unit suite is green, but the supplied sample flow fails and the frontend is still the default Vite template.

Top five fixes before the demo:

1. Wire the React frontend to upload files and render analysis/results.
2. Make the supplied sample datasets analyzable while preserving explicit ambiguous/quality warnings.
3. Fix comparator normalization for whitespace/case-only changes.
4. Return structured errors for invalid numeric parameters and complete recheck change metadata.
5. Disable debug/public binding and restrict CORS before any network-accessible demo.


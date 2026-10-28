# VoterLens AI Hackathon Demo Audit

Audit date: 2026-10-28  
Scope: backend, frontend, integration, documentation, responsible-AI behavior, privacy, and release hygiene.  
Change constraint: no existing source files were modified. Only audit tests and this report were added.

## 1. Executive summary

| Area | Result | Notes |
|---|---|---|
| Repository hygiene | PARTIAL | Virtual environments and `.env` are ignored, and no tracked production secret was found. However, the worktree was already dirty, two pytest configurations exist, and CSV fixtures are tracked. |
| Backend regression | PARTIAL | Existing suite: 102 passed, 87% total coverage from both roots. Requested audit suite: 6 passed, 1 failed because the requested `roll_before.csv`/`roll_after.csv` files do not exist. |
| Backend correctness | PARTIAL | Core category, rate, deterministic, recheck, and valid counterfactual contracts pass. Insufficient similar-peer handling has a reproducible 500 error. |
| Backend security/privacy | FAIL | Analysis-dependent endpoints have no authentication/authorization; short analysis IDs expose stored records and exports. Optional Gemini prompts include uploaded values without dataset-value sanitization/delimiters. |
| Frontend quality | PASS | `npm install`, lint, build, unit tests, and Playwright E2E completed successfully. Build emits a chunk-size warning. |
| Frontend integration | PARTIAL | The frontend can reach the backend with `VITE_API_BASE_URL`; live API flow completed. The documented Playwright setup uses ports 5053/4173, while the normal frontend default is backend 5000. |
| Responsible AI | PARTIAL | Disclaimers and deterministic fallback are present, but some simple/Hindi question responses omit evidence/alternatives/limitations/next step. |
| Documentation/spec compliance | PARTIAL | Endpoint documentation is broadly aligned, but fixture names/counts and some feature claims do not match the repository. |
| Demo readiness | NO-GO | The core happy path works, but the requested fixture contract is absent, insufficient-peer counterfactuals can crash, and the privacy/access-control posture is unsafe beyond a tightly controlled local synthetic demo. |

## 2. Step 1 — inventory and Git hygiene

### Project tree and roles

* `backend/`: Flask API and analysis engine.
  * `app.py`: application factory, API routes, in-memory analysis store, startup entry point.
  * `comparator.py`: record-ID matching, field diffs, category counts, area statistics.
  * `validator.py`: CSV schema, row validation, warnings, review flags, and ambiguous-row handling.
  * `detector.py`: deterministic area/data-quality finding detection and counterfactual comparisons.
  * `explainer.py`: Evidence Passport and simple/technical/Hindi finding explanations.
  * `insight_assistant.py`: deterministic bilingual summaries and optional Gemini chat path.
  * `reporter.py`: CSV exports.
  * `models.py`: Pydantic response/data models.
  * `config.py`: thresholds, limits, schema, and defaults.
  * `data/`: tracked synthetic CSV fixtures and expected outcomes.
  * `tests/`: existing unit/API/QA tests plus the new audit tests in `tests/audit/`.
* `frontend/`: React/Vite client.
  * `src/App.jsx`: navigation, ingestion, dashboard pages, findings, records, assistant, benchmark, and reports.
  * `src/api/client.js`: fetch wrapper and configurable backend URL.
  * `src/assistant/actions.js`: allowlisted local command parsing, draft CSV helpers, and action validation.
  * `src/utils/audit.js`: count reconciliation and presentation helpers.
  * `tests/`: unit and Playwright E2E tests plus the new audit test.
* Root `README.md`: local setup and demo notes.
* `backend/README.md`: backend setup and endpoint table.
* `frontend/README.md`: frontend setup, assistant, E2E, and privacy notes.

Filtered tree was printed with `find`, excluding `.git`, environments, caches, `node_modules`, and `frontend/dist`.

### Git findings

* `backend/.gitignore` ignores `venv/`, `.venv/`, `.env`, caches, logs, uploads, and reports. `frontend/.gitignore` ignores `node_modules`, build output, logs, and local env files.
* `git ls-files` showed tracked `backend/data/previous_roll.csv` and `backend/data/current_roll.csv`; no tracked `.env`, virtual environment, `node_modules`, private key, database, or file over 1 MB was found.
* `backend/.env` exists locally, is ignored, and was not printed in full. Its variable names include `GEMINI_API_KEY`; the value was redacted during the audit.
* A repository-wide source search found no hard-coded production API key, token, password, or private-key material. Matches were configuration names/documentation and the optional Gemini environment lookup.
* There are two pytest configurations: root `pytest.ini` and `backend/pytest.ini`. They select the same backend tests with different `pythonpath`/`testpaths` roots.
* The worktree was already dirty before this audit, including changes to `app.py`, frontend files, QA tests, and documentation. Those changes were not reverted or edited.
* `frontend/dist/` exists on disk but is not tracked. `frontend/playwright.config.js`, assistant sources, and frontend tests were already untracked when the audit began; they were not treated as source changes.

## 3. Step 2 — backend regression

### Environment and commands

* Python used: `Python 3.9.6`.
* `backend/requirements.txt` decoded as valid UTF-8.
* `./.venv-1/bin/python -m pip install -r backend/requirements.txt`: completed; all requirements were already satisfied.
* The documented backend virtual environment also installed the requirements successfully.
* `./.venv-1/bin/python -m pytest --cov=backend --cov-report=term-missing`: **102 passed in 2.25s**.
* `cd backend && ../.venv-1/bin/python -m pytest --cov=. --cov-report=term-missing`: **102 passed in 2.26s**.
* Both runs reported **87% total coverage**. Key module coverage: `app.py 80%`, `comparator.py 97%`, `detector.py 96%`, `explainer.py 82%`, `insight_assistant.py 84%`, `reporter.py 89%`, `validator.py 92%`.

### Earlier bug status

| # | Status | Evidence | File/line | Reproduction and expected vs actual | Suggested fix |
|---|---|---|---|---|---|
| 1 | FIXED (default) | Default host is loopback and debug is environment-controlled, default off. | `backend/app.py:1055-1059` | `./.venv-1/bin/python backend/app.py` attempted to start with debug off and loopback defaults. Expected: no debug/`0.0.0.0`; actual default meets that. Environment variables can still deliberately enable unsafe settings. | Keep production startup behind Gunicorn and reject unsafe production combinations (`FLASK_DEBUG`, public host) in deployment configuration. |
| 2 | FIXED (default) | Default CORS list is localhost ports, not `*`. | `backend/app.py:93-102` | `Origin: https://evil.example` received no `Access-Control-Allow-Origin`; `Origin: http://localhost:5173` is allowed. Expected: restricted origins; actual default is restricted. `CORS_ALLOW_ALL=1` remains an explicit bypass. | Remove the wildcard escape hatch in production or require an explicit non-development deployment guard. |
| 3 | FIXED | Values are normalized with trim, whitespace collapsing, and case folding. | `backend/comparator.py:41-54` | The audit hand-made formatting test passed: `"Alice Smith"` and `"  alice   smith  "` classify `UNCHANGED`, not `MODIFIED`. | Retain regression coverage. |
| 4 | FIXED for loadability, but fixture quality remains a release issue | Current sample analysis succeeds despite duplicate rows being classified ambiguous. | `backend/data/previous_roll.csv`, `backend/data/current_roll.csv`, `backend/validator.py:221-230` | POSTing both tracked samples to `/api/analyze` returned 200. Actual summary: previous 342/current 320, 2 ambiguous on each side. Expected requested fixtures are 300/280 and valid for analysis; actual requested filenames are absent and tracked samples still contain duplicate IDs. | Replace or regenerate committed fixtures to the documented/requested contract, or document the intentional ambiguous rows and update expected outcomes. |
| 5 | FIXED | Non-numeric threshold is caught and returns structured 400. | `backend/app.py:418-426` | POST `/api/compare-areas` with `"threshold_override":"not-a-number"` returned `400 {"code":"INVALID_THRESHOLD"}`. | Retain API regression test. |
| 6 | FIXED in response shape, PARTIAL in semantics | Response includes `dataset_changed` and `config_changed`. | `backend/app.py:508-526` | Recheck returned both fields and `match: true`. Actual code hard-codes `dataset_changed=False`; `config_changed` can be a false positive because the stored snapshot has fewer keys than the current config. | Persist a complete config snapshot and compare dataset fingerprints to the current dataset/config used for recheck. |
| 7 | FIXED | Unknown question keys return “I cannot answer that from this evidence…” in all supported language modes. | `backend/explainer.py:377-391` | Existing API regression test and direct code inspection confirm refusal rather than a menu. | Retain refusal tests for every supported language. |
| 8 | STILL OPEN | Some simple/Hindi Q&A templates contain only a rule/rate or a short verification sentence, not all required sections. | `backend/explainer.py:307-375` | Calling `what_evidence`, `what_percentage`, or `what_verify` in `simple`/`hindi` omits some of evidence, alternatives, limitations, or next step. Expected: every explanation carries rule, evidence, alternatives, limitations, and next step; actual varies by question/language. | Build all language/question responses from the same structured Evidence Passport sections and test required fields/text. |
| 9 | FIXED | Unknown columns are warnings and out-of-range ages are explicit review flags. | `backend/validator.py:158-173`, `backend/validator.py:280-315` | Existing validator tests passed for unknown columns and ages 16/130. Expected clear warning; actual structured warning/review flag with row, value, and threshold. | Keep warning text visible in the frontend validation summary. |

### Requested fixture check

The requested paths `backend/data/roll_before.csv` and `backend/data/roll_after.csv` do not exist. The available paths are `backend/data/previous_roll.csv` and `backend/data/current_roll.csv`.

Observed available fixture counts:

| File | Rows | Duplicate IDs | Non-numeric ages | Out-of-range ages |
|---|---:|---:|---:|---:|
| `previous_roll.csv` | 342 | 1 duplicate value | 0 | 0 |
| `current_roll.csv` | 320 | 1 duplicate value | 0 | 0 |

The live sample summary was:

`previous_records=342, current_records=320, added=60, deleted=82, modified=11, unchanged=247, ambiguous_previous=2, ambiguous_current=2`.

This does not match the requested `300/280`, `9 added`, `29 deleted`, `12 modified`, A01 40%, A02-A06 2-6%, and ages 16/130 expectations. The requested canonical fixture cannot be verified because it is not present.

### Server startup

* The documented startup path worked on port 5054 when `PORT=5054` was supplied and returned HTTP 200 from `/api/health`.
* The default startup path uses port 5000 and loopback host by source inspection.
* A port-5000 process was already listening. The audit's attempted second launch returned the exact error: `Address already in use ... Port 5000 is in use by another program.` It was not terminated.
* `lsof` showed the Python service listening on `127.0.0.1:5000`; the unrelated macOS `ControlCenter` listener also appeared on `*:5000`, so port ownership should be made explicit in demo instructions.

## 4. Step 3 — audit tests and correctness

Added [backend/tests/audit/test_release_contracts.py](backend/tests/audit/test_release_contracts.py) with seven tests covering:

* previous/current reconciliation and disjoint categories;
* an exact hand-made added/deleted/modified/unchanged pair;
* per-area `deleted / previous_count` rates;
* deterministic repeated comparisons;
* recheck reproduction;
* all-area and similar-area counterfactual baselines plus a small-group warning;
* the requested fixture names/counts.

Command and result:

```text
7 collected
6 passed
1 failed
FAILED test_requested_sample_fixture_counts_are_present
Failed: Requested fixtures backend/data/roll_before.csv and roll_after.csv are missing
```

The valid counterfactual path passed after correcting the audit test to the actual response shape (`new_comparison`). During testing, a two-peer `similar_areas` request reproduced a separate server error: `TypeError: unsupported format string passed to NoneType.__format__` at `backend/detector.py:460`. This is a new High bug documented below.

## 5. Step 4 — frontend audit

### Commands and results

* `cd frontend && npm install`: completed; npm reported 69 packages audited and **0 vulnerabilities**.
* `npm run lint`: exit 0, no lint diagnostics.
* `npm run build`: exit 0. Vite transformed 2512 modules and emitted a warning that the minified JS chunk is 669.31 kB, above the 500 kB threshold.
* `npm test`: **7 passed, 0 failed**.
* `node --test tests/audit/release-audit.test.js`: **2 passed, 0 failed**.
* `npm run test:e2e`: exit 0; Playwright ran 10 tests across Chromium and mobile Chromium. Its configured web servers use a separate backend on 5053 and Vite on 4173.

### Behavior

* `src/assistant/actions.js` parses a finite set of local commands, validates context and editable fields, and handles CSV draft parsing/serialization. It does not call an AI service.
* `src/utils/audit.js` reconciles backend counts and formats numbers, percentages, timestamps, records, and finding metrics.
* `src/api/client.js:1` uses `VITE_API_BASE_URL` when present, otherwise `http://127.0.0.1:5000`. This matches the backend default port, while the Playwright configuration overrides it to 5053.
* The frontend assistant calls backend `/api/chat/*` only through `fetch`. Optional Gemini use is backend-controlled and explicitly opt-in from the UI; no frontend API key is present.
* React renders uploaded/API values as normal JSX text. No `dangerouslySetInnerHTML`, direct `innerHTML`, or unescaped CSV HTML sink was found.
* The UI visibly labels data as synthetic and says findings are not proof of wrongdoing. Names are shown in record-oriented screens and can be included in exports, which is documented as local-demo-only.
* Ingestion has loading/error/success notices and backend health status. Empty workspace pages are guarded by an empty-state prompt. Backend-offline health is represented as disconnected and actions surface fetch errors.
* Basic labels/roles, navigation buttons, table headers, a mobile menu, keyboard-oriented assistant controls, and a Playwright focus smoke test are present. A full WCAG contrast audit was not possible from static inspection alone.

## 6. Step 5 — integration

The frontend was started with `VITE_API_BASE_URL=http://127.0.0.1:5000 npm run dev -- --host 127.0.0.1 --port 5173` and returned HTTP 200 for `/`. The backend allowed `Origin: http://localhost:5173` and rejected an unrelated origin.

The complete API-backed flow was exercised live:

| Step | Result | Evidence |
|---|---|---|
| Load sample data | PASS | Metadata and both CSV downloads returned 200. |
| Analyze/show summary | PASS | Analysis returned 200 with the observed 342/320 summary above. |
| Added/deleted/modified records | PASS | Change lists returned; `/api/record/...` returned 200 for `MOD-0096`. |
| Open flagged area | PASS | `/api/compare-areas` returned 200 and a flagged B01 comparison. |
| Evidence Passport/Recheck | PASS | Recheck returned `match=true`, `dataset_changed=false`, `config_changed=true`. |
| False-Alarm Challenge | PASS | Returned 200, `passed=10`, `failed=0`, precision/recall 1.0, and 10 scenario results. |
| Export report | PASS | Findings export returned 200, `text/csv`, 1611 bytes. |
| Closing line | PARTIAL | The UI contains responsible-use copy, but the requested exact closing-line wording was not specified or separately tested. |

The Playwright suite also passed its assistant, draft edit, undo, Hindi/Hinglish, opt-in, unknown-record, invalid-age, mobile, and keyboard scenarios. It is not a complete automated assertion of every requested eight-step screen transition.

## 7. Step 6 — responsible AI and privacy

* Searches found explicit non-accusatory wording in backend disclaimers and the frontend privacy banner: anomalies are signals for review and not proof of fraud/wrongdoing.
* Fraud/rigging questions are denied or reframed by deterministic responses. Unknown evidence questions are refused.
* Finding objects generally carry `rule_id`, evidence, possible explanations, limitations, and recommended next step. The simple/Hindi question templates do not consistently expose all of those fields, which is the open Bug 8.
* Uploaded analyses are retained in a bounded in-memory LRU and disappear on restart; there is no durable cleanup endpoint. README documentation states this limitation.
* Names and uploaded fields can appear in record responses and CSV exports. They are not written to ordinary request logs by the inspected code, but unauthenticated analysis IDs expose them to anyone possessing/guessing an ID.
* The optional external AI path includes uploaded-derived area/finding values in `facts` without sanitizing every dataset-derived string or using a clearly separated untrusted-data channel.

## 8. New bugs, ordered by severity

### Critical

No Critical findings were confirmed.

### High

#### H-1 — Similar-area counterfactual can return HTTP 500 for insufficient peers

* **File/line:** `backend/detector.py:418-475`, especially line 460.
* **Reproduction:** Analyze a valid dataset with a target area and fewer than three comparable peers, then POST `/api/compare-areas` with `{"comparison_method":"similar_areas"}`.
* **Expected:** HTTP 200 with an explicit “Insufficient comparison group” warning, as required by the API contract.
* **Actual:** The audit reproduced `TypeError: unsupported format string passed to NoneType.__format__` while formatting a `None` baseline; the endpoint returns the generic 500 response.
* **Suggested fix:** Branch before formatting/explaining when `new_baseline is None`; return the structured warning response and no numeric comparison.

#### H-2 — Analysis IDs do not authorize access to records, exports, or assistant data

* **File/line:** `backend/app.py:535-652`, `backend/app.py:955-1048`.
* **Reproduction:** Upload two CSVs, capture `analysis_id`, then from an unrelated unauthenticated client request `/api/export/<analysis_id>/added` or `/api/record/<analysis_id>/<record_id>`.
* **Expected:** Authentication/ownership enforcement, or a full-length cryptographic capability token with explicit sharing semantics.
* **Actual:** Possession of an eight-hex-character suffix ID is sufficient to retrieve stored data; no authentication or ownership check exists.
* **Suggested fix:** Add authentication/authorization for every analysis-dependent endpoint. If anonymous local sharing is intentional, use high-entropy capability tokens, avoid existence-revealing behavior where possible, and redact personal fields by default.

### Medium

#### M-1 — Recheck falsely reports configuration changes and never detects dataset changes

* **File/line:** `backend/app.py:364-368`, `backend/app.py:508-526`.
* **Reproduction:** Analyze any dataset and call `/api/recheck-finding`; compare the stored snapshot with the current configuration.
* **Expected:** `config_changed` reflects a real configuration difference, and `dataset_changed` reflects changed source fingerprints.
* **Actual:** The stored snapshot contains only three keys, while recheck compares seven keys, so `config_changed` can be true without a real change. `dataset_changed` is hard-coded false.
* **Suggested fix:** Store the complete config snapshot at analysis time and compare fingerprints of the current source files or explicitly state that recheck is against the immutable stored dataset.

#### M-2 — Optional Gemini prompt is vulnerable to uploaded-data prompt injection

* **File/line:** `backend/insight_assistant.py:270-310`, `backend/insight_assistant.py:434-456`.
* **Reproduction:** Upload a valid CSV with an `area_name` containing instructions such as `Ignore all previous instructions...`, opt into external AI, and send a chat question.
* **Expected:** Uploaded field values are inert data and cannot modify model instructions.
* **Actual:** `facts` is interpolated with `str(facts)` into the same prompt text as system rules; only the chat message is sanitized.
* **Suggested fix:** Serialize facts as structured JSON, sanitize/length-limit all dataset-derived strings, delimit them as untrusted data, and use provider-supported system/instruction separation plus strict output validation.

#### M-3 — Requested canonical fixtures are missing and available samples do not meet the release contract

* **File/line:** `backend/data/` and `backend/data/expected_outcomes.json`.
* **Reproduction:** `test_requested_sample_fixture_counts_are_present` in the audit suite fails because `roll_before.csv` and `roll_after.csv` are absent; available files yield 342/320 rows and the summary above.
* **Expected:** The stated 300/280 fixture with the requested category/rate/age outcomes.
* **Actual:** Different filenames, counts, category totals, and no observed ages 16/130.
* **Suggested fix:** Commit the canonical synthetic fixtures or update the specification and all expected outcomes/docs to the actual fixture contract.

### Low

#### L-1 — Production bundle exceeds the configured Vite chunk warning threshold

* **File/line:** generated build output from `frontend/src/App.jsx` and dependency graph; no source line is a correctness failure.
* **Reproduction:** `cd frontend && npm run build`.
* **Expected:** A code-split or threshold-compliant production bundle.
* **Actual:** Build passes but warns that the minified JS chunk is 669.31 kB, above 500 kB.
* **Suggested fix:** Lazy-load large pages/charts or configure an evidence-based chunk limit after measuring demo performance.

## 9. Feature status

| Feature | Status | Evidence |
|---|---|---|
| CSV upload and validation | DONE | Ingestion UI, `/api/analyze`, schema checks, warnings/review flags, and tests. |
| Basic anomaly detection | DONE | Deterministic detector and finding tests. |
| Search and filter | PARTIAL | Record/area views and filters exist, but no comprehensive search behavior was found in the inspected UI. |
| CSV reports | DONE | Summary, added, deleted, modified, findings, and area comparison exports are implemented and live export returned 200. |
| Electoral Change Detective | DONE | Findings/area analysis and non-accusatory explanations are implemented. |
| Record-Level Change Tracker | DONE | Added/deleted/modified lists and `/api/record` field-level inspection. |
| Evidence Passport with Recheck | DONE | Evidence data and recheck endpoint/UI are present; change-flag semantics need M-1 correction. |
| Record Change Inspector | DONE | Record endpoint and frontend inspector are present. |
| False-Alarm Challenge | DONE | `/api/challenge/run` returned 10/10 passed with precision/recall 1.0 on synthetic scenarios. |
| Roll Timeline | MISSING | No distinct timeline page/endpoint was found in the navigation or endpoint list. |
| Counterfactual Audit Lab | PARTIAL | Valid all/similar-area flows work, but insufficient similar peers can produce H-1. |
| Multilingual explanation assistant | PARTIAL | English/Hindi/Hinglish paths exist; some simple/Hindi responses omit required Evidence Passport sections. |
| Isolated analysis sandbox | PARTIAL | In-memory bounded LRU isolates analyses within one process, but there is no authentication/authorization or durable tenant isolation. |

## 10. Test and coverage numbers

| Suite | Result |
|---|---|
| Backend existing suite from root | 102 passed; 87% total coverage |
| Backend existing suite from `backend/` | 102 passed; 87% total coverage |
| Backend audit suite | 6 passed, 1 failed (missing requested fixtures) |
| Frontend lint | Passed |
| Frontend production build | Passed with 669.31 kB chunk warning |
| Frontend unit tests | 7 passed |
| Frontend audit tests | 2 passed |
| Playwright E2E | 10 passed across desktop/mobile Chromium |
| npm audit | 0 vulnerabilities reported by `npm install` |

## 11. Demo-readiness verdict

**NO-GO for the requested eight-step live demo as specified.**

The happy path can be demonstrated locally with the currently available sample files: load, summary, change records, flagged area, recheck, challenge, and export all returned successful responses. However, it cannot honestly be called compliant with the stated demo contract because:

1. the named canonical fixtures and expected numbers are absent;
2. an insufficient similar-area comparison can crash the API;
3. recheck change flags are not semantically reliable;
4. record/export endpoints have no access control; and
5. some bilingual explanations are incomplete.

For a tightly controlled synthetic localhost-only hackathon presentation, the live happy path is **conditionally usable after a pre-demo check** of the sample counts and avoidance of insufficient-peer counterfactuals. It is not ready for public, shared, or real-person data.

## 12. Top five fixes before demo

1. Fix H-1 so insufficient similar-area data returns a structured warning instead of HTTP 500.
2. Resolve M-3 by supplying the canonical fixtures or correcting the written expected contract and sample-data narrative.
3. Correct M-1 so Recheck reports real dataset/config changes and does not show false positives.
4. Complete all simple/Hindi Evidence Passport sections and add assertions for rule, evidence, alternatives, limitations, next step, and “not proof” wording.
5. Add access control or, for a localhost-only demo, a clearly enforced demo mode that prevents public binding and redacts record-level exports; also sanitize all dataset-derived values before optional Gemini prompting.

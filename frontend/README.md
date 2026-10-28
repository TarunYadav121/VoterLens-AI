# VoterLens AI Frontend

The React/Vite frontend provides the VoterLens AI synthetic electoral-roll
comparison dashboard. It uploads two CSV releases to the Flask backend and
displays deterministic comparison counts, evidence-backed findings, area
analytics, record diffs, counterfactual checks, multilingual explanations,
the synthetic false-alarm benchmark, and CSV reports.

## Conversational assistant

The assistant supports deterministic, allowlisted commands without Gemini:

- Show findings or open the highest-priority finding.
- Inspect a record returned by the active analysis.
- Recheck the selected finding.
- Explain a returned finding's calculation.
- Navigate to a supported section or download a supported CSV report.
- Propose a change to an editable field in the current synthetic draft.

Draft edits always show a before/after confirmation card. Confirmed edits
create a new browser-session draft, preserve the original file, rerun the
normal analysis endpoint, and can be undone one change at a time. Unknown,
duplicate, or invalid records are rejected rather than guessed. This is a
session-level prototype history, not an official correction or certified audit
trail.

## Local setup

```bash
cd frontend
npm install
npm run dev
```

The backend should be running at `http://127.0.0.1:5000` first:

```bash
cd backend
source venv/bin/activate
python app.py
```

Set `VITE_API_BASE_URL` when the backend uses another local URL. Copy
`.env.example` to `.env.local`; do not put backend secrets in frontend
environment files.

## Checks

```bash
npm run lint
npm test
npm run build
```

## Browser tests

Browser tests use Playwright and are intentionally separate from the
dependency-free action tests:

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

The Playwright suite starts the local Flask backend on port `5053` and Vite on
port `4173`. Browser binaries are installed per machine and are not committed
to the repository. If browser installation is unavailable, report the suite as
not run rather than treating a build or action test as browser verification.

## Safety and limitations

- Use synthetic demonstration data only. Do not upload real voter information.
- Findings are statistical signals for human review, not proof of fraud or
  wrongdoing.
- The default assistant is deterministic and evidence-grounded. The optional
  external-AI path requires an explicit per-chat opt-in and is configured only
  on the backend.
- Backend analyses are stored in a bounded in-memory LRU and disappear when
  the backend restarts.
- Record-level exports can contain uploaded fields and are intended only for a
  controlled local demonstration. Authentication and authorization are required
  before using the service with real personal data or public users.
- The benchmark reports the actual results returned by the backend's ten
  synthetic scenarios. It does not establish real-world electoral performance.

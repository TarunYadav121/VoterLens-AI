# VoterLens AI

VoterLens AI compares two fictional electoral-roll CSV releases with
deterministic, explainable rules. It classifies added, deleted, modified,
unchanged, and ambiguous records, then reports area-level signals for human
review. A finding is never proof of fraud or wrongdoing.

## Run locally

Start the backend first:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://127.0.0.1:5000`; set
`VITE_API_BASE_URL` in `frontend/.env.local` for another backend URL.
Backend host, port, debug mode, and CORS origins are configured through the
backend environment. Use a production WSGI server rather than Flask's
development server for deployment.

## Data and privacy boundaries

The checked-in rolls under `backend/data/` are synthetic demonstration data.
Do not upload real voter information. The backend accepts CSV files up to
20 MiB and 100,000 rows, retains at most 10 analyses and an estimated 100 MiB
of uploaded input bytes in memory, and loses analyses on restart. Record-level
exports may include uploaded fields and are intended only for a controlled
local demo; authentication, authorization, retention, and redaction are
required for public or personal-data deployments.

Deterministic explanations are the default. Optional Gemini processing is
backend-only, disabled by default, and requires backend configuration plus an
explicit per-chat opt-in. Only aggregate audit facts are sent to the
provider.

## Checks

```bash
cd backend
pytest tests -q

cd ../frontend
npm run lint
npm run build
```

The false-alarm benchmark reports the actual results of its controlled
synthetic scenarios. Those results do not establish real-world electoral
performance.
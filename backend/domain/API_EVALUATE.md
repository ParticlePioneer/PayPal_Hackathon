# Isolated negotiation HTTP comparison

This development-only command sends turns to the existing
`POST /api/negotiations/{id}/turn` endpoint and reads each saved conversation
with `GET /api/negotiations/{id}`. It starts an in-process test application,
uses synthetic cases and creates an isolated disposable PostgreSQL schema per
case. It does not mount new routes in the application, contact Render, or make
payment calls. Quotes exist only in each temporary schema, which is removed.

Use a disposable PostgreSQL database whose account can create and drop schemas.
Set `TEST_DATABASE_URL` explicitly; `DATABASE_URL` is never used as a fallback.
Do not run this tool concurrently in the same Python process: it temporarily
wraps the agent boundary to measure sanitized role, error category, and timing.
The output excludes private inputs and provider messages. HTTP error results
are not complete negotiations. The `competing_buyer_depleted` scenario is an
already-depleted snapshot, not a concurrent buyer test.

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.api_evaluate --candidate fixture
.\.venv\Scripts\python.exe -B -m backend.domain.api_evaluate --candidate live --env-file .env
```

Fixture mode is simulated and makes no model calls. Live mode uses the explicit
configured model and key; it may consume quota. Both modes have a six-turn cap
and a 30-second per-turn boundary. An exit code of 0 means each scenario matched
its expected outcome. Neither mode proves the deployed service or real merchant
policy works. A timeout includes local worker startup and remote request time;
it does not establish which component caused the delay.

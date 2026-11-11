# A1 verification status

Recorded November 11, 2026, after the explicit selection of `gemini-3.8-flash`.
This is a verification record, not a claim that A1 or A2 passed its live gate.

## Implemented and tested

- A1.1 typed actions, cumulative delivery requirements, fixed business fixtures,
  role-specific private inputs, and controlled public transcript rendering.
- Server-side Gemini configuration, one-action client, and terminal smoke command.
- Gemini 3 compatibility: no explicit candidate count; the parser still requires
  exactly one returned candidate.
- Optional `GEMINI_THINKING_LEVEL=low|medium|high`. No default override; unsupported
  values fail local validation, and unsupported model settings fail at the provider.
- Safe failure diagnostics expose only a known error code and optional HTTP
  status, not credentials, request data, raw provider output, or private reasoning.

No packages were added or upgraded during this verification task. All modified
code is under `backend/domain/`; other team members' files were not edited.
The existing root `.env.example` modification was left untouched. The configured
key was checked without printing it and was not found in that tracked example.

## Commands and observed evidence

Run from the repository root, using the project's Python 3.12 virtual environment:

```powershell
$env:GEMINI_MODEL = 'gemini-3.8-flash'
$env:GEMINI_TIMEOUT_MS = '60000'
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke

$env:GEMINI_THINKING_LEVEL = 'low'
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke

.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_model_client.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
```

Observed outcomes:

- The first live request timed out. No fallback or automatic retry was used.
- The explicit low-thinking request exited 1 with
  `code=provider_unavailable, http=503`. No action was accepted or fabricated.
- Model-client tests: **68 passed**.
- Full backend regression: **344 passed, 1 warning** in 9.49 seconds.
- The warning is pytest collection of the existing payment-owned `TestQuote`
  dataclass; payment tests still ran. That file was not changed.

Offline tests use synthetic credentials and mocked provider responses. Their
passing status is not proof of working provider generation. Earlier model-list
success demonstrated a valid metadata request, not inference availability.
The real key and root `.env` were never displayed or modified by this task.

## Five-perspective review after local tests

The implementation assistant applied these thinking perspectives directly;
there were no independent reviewers or separate approvals.

- **Contrarian:** A valid configuration or successful model listing cannot stand
  in for a real parsed action. Keep A1's live gate unpassed after HTTP 503.
- **First Principles Thinker:** Settings control resource use; action contracts
  and acceptance eligibility remain separate. No negotiation state was added.
- **Expansionist:** Explicit thinking configuration supports latency tuning while
  preserving omitted-setting behavior and avoiding automatic model fallback.
- **Outsider:** Error code/status and this record distinguish operational failure
  from local test success without exposing raw provider details.
- **Executor:** Focused and backend regressions passed. Stop repeated live calls
  after a confirmed transient failure rather than manufacturing evidence.

## Remaining prerequisites

1. Retry the actual smoke command when provider inference is available. A1 is
   complete only after a real action parses with the configured model.
2. The seller's minimum inclusive total for the 30-shirt order still requires a
   team-provided integer-cent value. Do not derive it from fixture offer prices.
3. A2's two-agent runner is authorized but has not been implemented because A1's
   required live gate remains unmet. No A3 or later work has started.

References: [model and thinking-level guidance](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8)
and [provider troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting).

## Subsequent authorization

After the verification record above, the user explicitly authorized proceeding
with A2 offline while keeping real-model acceptance pending. See
[NEGOTIATION.md](NEGOTIATION.md) for that implementation and its boundaries.
The earlier test results and live failure evidence above are unchanged. This
authorization does not turn a failed live smoke into a passing A1 gate.

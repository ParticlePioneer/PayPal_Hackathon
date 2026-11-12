# A1 verification status

This document records historical Gemini verification. The current integrated
provider is OpenRouter; see [OPENROUTER.md](OPENROUTER.md) and
[A6_RELEASE.md](A6_RELEASE.md) for current configuration and release status.

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

## Follow-up verification — November 12, 2026

The configured model was explicitly selected as `gemini-3.8-flash` for this
attempt. Configuration validation passed, but a real buyer-action smoke request
returned `code=timeout, http=504`. No action was accepted. A1's live acceptance
gate remains open, and this response does not establish that the credentials
or model can complete generation.

The seller's actual minimum inclusive price remains a team decision. The
existing 30000-cent floor is an explicitly synthetic development input only;
it is not merchant approval and must not become a default commercial policy.
An optional live-model demonstration may use that synthetic scenario if clearly
labeled, but it cannot demonstrate merchant-approved terms. A2's live gate
still requires an actual completed model negotiation, separately from offline
fixture results. Before merchant-backed integration, the team must supply the
real seller policy and verify the resulting flow.

Focused A1/A2 offline regression after this attempt: 418 passed. No provider
output, private inputs, or credentials are recorded here.

## Further live retry — November 12, 2026

The authorized `gemini-3.8-flash` buyer-action smoke was retried with a
60000 ms timeout and low thinking; it again returned HTTP 504 without an
action. A separate minimal generation request to the same model, containing
only a non-sensitive prompt and no negotiation schema, also returned HTTP 504.
This shows the failure is not limited to the structured negotiation request;
it does not identify whether the cause is the provider, account, or network
path. The first diagnostic invocation had a command-line quoting error and made
no request; the corrected invocation produced the result above.

A1 and A2 live gates remain unverified. The A2 live negotiation was not run
because A1 did not produce an action. Do not replace this result with a fixture
or present the synthetic seller minimum as merchant policy.

The model catalog subsequently listed both `gemini-3.8-flash` and
`gemini-3.7-flash` as generation-capable. Listing confirms only catalog access,
not successful inference. With explicit user authorization, a 3.7 Flash smoke
request and a separate minimal, non-sensitive generation request both returned
HTTP 503. Neither request produced an action. The local `.env` was not changed.
The A1 and A2 live gates remain open.

## Live verification with Gemini 3.6 Flash — November 12, 2026

After a further 3.8 Flash HTTP 504 and a 3.7 Flash HTTP 503, non-sensitive
minimal API diagnostics returned HTTP 200 with candidates for 3.6 Flash and 3.5
Flash. Gemini 3.6 Flash then passed the real buyer structured-action smoke test:
the returned `offer` parsed successfully. A separate spawned-worker check also
parsed an action. These are real provider calls, not fixture responses.

The first real 3.6 two-agent attempt stopped with a retryable model error on
turn one and produced no agreement. A subsequent real run, using explicitly
synthetic stock and seller policy, completed in three turns: a buyer proposal,
a seller counter for 12 navy Friday and 18 black Monday at 35400 cents, and a
buyer acceptance. The A2 server accepted the split terms; the terminal runner
issued no quote, reserved no stock, and initiated no payment. The first worker
diagnostic command had a local import-path error and made no provider request;
its corrected retry succeeded.

The user subsequently approved setting the ignored local `.env` model to
`gemini-3.6-flash`; other parsed settings, including the API key, were preserved.
These checks establish A1's model-action gate and the A2 live negotiation gate
for this configured model and synthetic scenario. They do not establish real
merchant policy, complete A5 live evaluation results, or integrated checkout.

After the user's approved 3.6 Flash A5 live comparison, a separate minimal
generation diagnostic returned HTTP 429 `RESOURCE_EXHAUSTED`. A second
sanitized request indicated a daily limit and a retry delay of 33910 seconds.
This does not prove the causes of prior 503/504 responses or every failed A5
model call. The corrected A5 comparison remains incomplete; see
[A5_EVALUATION.md](A5_EVALUATION.md).

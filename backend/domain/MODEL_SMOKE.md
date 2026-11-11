# A1 model configuration and structured-action smoke check

This task adds one Gemini action call per invocation. It does not implement the
A2 negotiation loop, commercial validation, quote issuance, stock reservations,
database work, payment integration, or HTTP routes.

## Install and configure

Use the project Python 3.12 virtual environment from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m pip install -r backend/domain/requirements-dev.txt
```

New domain-local dependencies: official `google-genai>=1.75,<2`,
`python-dotenv>=1.2,<2`, and `httpx>=0.28.1,<1` (also required by the SDK;
declared explicitly for transport-error handling). Shared backend requirements and deployment configuration
are unchanged; deployments must explicitly install domain requirements until B
coordinates integration. Tested versions are recorded in the task report.

Set these variables locally in the process environment or the ignored root
`.env`. Never put real credentials in documentation, terminal arguments, tests,
source files, or chat:

- `GEMINI_API_KEY`: a server-side key authorized to use the model.
- `GEMINI_MODEL`: the actual model ID available to your account. Required; there
  is no default, fallback, or automatic model discovery. Use the bare `gemini-...`
  name, without a `models/` prefix or URL.
- `GEMINI_TIMEOUT_MS`: optional integer, 1000 through 60000; default 30000.
- `GEMINI_MAX_OUTPUT_TOKENS`: optional integer, 128 through 4096; default 2048.
- `GEMINI_THINKING_LEVEL`: optional `low`, `medium`, or `high`; omitted by
  default, preserving the model's default. Set `low` explicitly for a
  latency-sensitive Gemini 3.8 action call. Model support must be checked;
  unsupported settings fail rather than silently changing the request.

The CLI reads only the root repository `.env` if it exists, or exactly the file
selected by `--env-file`. The settings loader itself never discovers files.
Process variables take precedence, including explicitly empty values. Dotenv
interpolation is disabled. The loader never changes `os.environ` or imports
PayPal configuration into model requests.

## Offline check and real smoke command

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke --check-config
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke
```

`--check-config` validates local configuration, not credentials or provider
access. Without that flag, the command makes one real, potentially billable
generation request using the buyer fixture and only the buyer's private budget.
The fixture dates stay fixed; no seller floor, stock, or Monday-only color is
invented. The model may return any valid action. A parseable response is A1
provider evidence, not evidence of a valid deal or fulfilled order.

For a different input or explicit seller input:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke --env-file .env --role buyer --input path/to/private-buyer.json
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke --role seller --input path/to/private-seller.json
```

Input files must match `BuyerAgentInput` or `SellerAgentInput`, respectively.
Seller smoke requires an explicit file so no commercial policy is invented.
Keep files containing private data outside tracked source. Input files and
serialized role payloads are limited to 128 KiB. This CLI does not log their
contents.

Exit 0 means configuration checked or a real action parsed, as stated by the
message. Exit 1 means configuration, input, transport, provider, or action
validation failed. Argparse uses exit 2 for invalid flags. Success prints only
model ID, role, and action type. No raw response, private terms, prompt, key, or
provider error body is printed. Failed calls are never replaced with fixtures.
Failures include a safe error code and HTTP status when available; these are
diagnostic metadata, not raw provider messages.

## Client and wire contract

`GeminiActionClient.generate_buyer(BuyerAgentInput)` and
`generate_seller(SellerAgentInput)` each construct a fresh request. There is no
conversation session or cross-role history. Supplied Pydantic instances are
revalidated before being sent. The current role's private data is intentionally
sent to the configured Gemini provider; it is not sent to the opposite role or
published as transcript text. Provider data-handling policy is outside this
client's enforcement boundary.

The transport uses the Gemini Developer API at
`https://generativelanguage.googleapis.com/v1beta`, an explicit API key, a bounded
SDK HTTP timeout, output-token limit, and one attempt. The request omits
`candidate_count` for Gemini 3+ compatibility; parsing still requires exactly
one returned candidate. It never
uses Vertex/Enterprise credentials or tools. An HTTP timeout is not an exact
end-to-end wall-clock deadline; negotiation-level deadlines remain A2 work.

Gemini receives an object containing `action`, whose schema is derived from the
existing discriminated action union. The provider schema replaces `oneOf` with
disjoint `anyOf` branches, constants with one-value enums, and positive-integer
bounds with `minimum: 1`. Local Pydantic validation remains authoritative. The
provider envelope does not change C's public API or B's quote adapter contract.

Only a single candidate with a normal `STOP` finish and valid action JSON is
accepted. Blocked, truncated, empty, ambiguous, duplicate-key, nonfinite-number,
unexpected-field, or otherwise malformed responses fail closed. Reasoning parts
are skipped. Markdown extraction and automatic output repair are unsupported.
SDK client resources are closed on both success and failure.

`ModelCallError.code` identifies safe error categories; `retryable` describes
whether the caller could retry later. No automatic retries occur. Never log
raw SDK exceptions, requests, responses, or role inputs. Third-party SDK/HTTP
debug logging must remain disabled when handling private inputs.

## Local evidence

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_model_config.py backend/domain/tests/test_model_client.py backend/domain/tests/test_model_smoke.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pip check
```

The tests use synthetic credentials and mocked provider responses, including
the actual installed SDK with an in-memory HTTP transport. They are not live
provider evidence. The live CLI is never run automatically by pytest. Real
provider access and schema support remain unverified until an actual configured
smoke command succeeds. No full A1 completion follows from offline tests alone.

References: [official SDK documentation](https://googleapis.github.io/python-genai/)
and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

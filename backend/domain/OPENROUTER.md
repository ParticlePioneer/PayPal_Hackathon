# OpenRouter model client

The live domain model source is `OpenRouterActionClient`. It requests one JSON
action per buyer/seller turn using `dots-studio/dots-3-note-preview:free`, with
4096 output tokens and a 30000 ms timeout by default. Configure these explicitly
in the root `.env` or server environment:

```dotenv
OPENROUTER_API_KEY=your-server-side-key
OPENROUTER_MODEL=dots-studio/dots-3-note-preview:free
OPENROUTER_TIMEOUT_MS=30000
OPENROUTER_MAX_OUTPUT_TOKENS=4096
```

Keep the key server-side. Only explicit `:free` model IDs are accepted; there
is no silent fallback to another model or fixtures. Free provider capacity and
quota can cause failures, and the current model has produced ineligible offers
and timeouts in synthetic tests. Obtain appropriate provider data-handling terms
before sending real buyer budgets or merchant policy. Gemini's existing module
is retained for historical compatibility; the live runners use OpenRouter.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke --check-config
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate live --env-file .env
```

Evaluation uses six synthetic scenarios, a six-turn maximum, a 30-second
per-turn deadline and a 180-second per-case deadline. It prints the accepted
conversation and all attempted actions or errors for each case. A timeout or
provider error is incomplete, and an unexpected outcome makes the CLI fail.
No stock is reserved or quote issued by this in-memory runner. Do not run
evaluations concurrently in one process: turn capture temporarily wraps the
agent boundary. To capture the raw HTTP bodies, opt in using
`--response-trace openrouter-response-local.jsonl`; these bodies can contain
sensitive content even though keys and selected headers are redacted. The
suggested filename is gitignored. No trace exists if there is no HTTP response.

The host can construct a live source as follows:

```python
from backend.domain.openrouter_client import OpenRouterActionClient
from backend.domain.openrouter_config import Settings

agent_source = OpenRouterActionClient(Settings.from_environment())
```

Pass it to `NegotiationService` along with the quote adapter and trusted seller
factory. The integrated host mounts the router when `B4_ENABLED=true` and
requires its session, database, and merchant policy configuration. See
[API.md](API.md) and [payments setup](../payments/README.md).

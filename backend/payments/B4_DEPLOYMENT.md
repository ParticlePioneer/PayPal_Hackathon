# B4: OpenRouter negotiation and PayPal Sandbox checkout

B4 connects the live OpenRouter client to the domain's PostgreSQL quotes and
the existing PayPal authorization endpoints. Inventory, fulfillment and the
30000-cent seller floor are simulated demo policy. Model and Sandbox calls in
the deployed acceptance run must be real; automated provider stubs are not
evidence that this live gate passed.

## Configure the existing Render web service

Use the web service's Environment page. An ordinary Git push is not proof that
an existing service has picked up changes from `render.yaml`; verify these
values on the service itself. Keep its existing database, session secret and
Sandbox app credentials.

| Variable | Value for B4 acceptance |
| --- | --- |
| `B4_ENABLED` | `true` |
| `OPENROUTER_API_KEY` | Server-side OpenRouter key |
| `OPENROUTER_MODEL` | Explicit tested `:free` model ID; repo default is `dots-studio/dots-3-note-preview:free` |
| `OPENROUTER_TIMEOUT_MS` | `30000` initially; allowed range 1000–60000 |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | `4096`; allowed range 128–4096 |
| `MERCHANT_MINIMUM_TOTAL_CENTS` | `30000` for the explicitly simulated demo |
| `DATABASE_URL` | Existing team PostgreSQL URL |
| `SESSION_SECRET` | Existing random secret of at least 32 characters |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Existing Sandbox REST app credentials |
| `B2_RUN_MIGRATIONS` | `true` for the coordinated migration deployment |
| `B2_HARNESS_ENABLED`, `B3_CAPTURE_ENABLED`, `B3_ALLOW_FAULT_INJECTION` | `false` |

`B4_MERCHANT_TOKEN` is optional for buyer checkout; configure a separate random
secret of at least 32 characters if merchant reconciliation is needed. Never
put model keys or merchant tokens in `VITE_*` variables. No Gemini key is used
by B4. Keep `google-genai` installed: OpenRouter currently reuses the domain
validator's SDK response types.

The Blueprint leaves B4 and migrations disabled initially. Enable them for the
coordinated acceptance deployment. Model requests begin on negotiation turns,
not during startup or `/health` checks. The configured timeout is also the
total worker deadline, including process startup; increasing it does not fix
provider rate limits or guarantee a successful response.

## Check before deployment

From the repository root with your virtual environment activated:

```powershell
python -B -m backend.domain.model_smoke --check-config
python -B -m backend.domain.model_smoke
python -B -m unittest discover -s backend/payments/tests -v
```

The smoke command reads the root `.env` when present; process environment
values take precedence. The first command is offline. The second makes one
real OpenRouter call and should report `OpenRouter smoke passed`. This verifies
one parsed action, not a completed negotiation. Do not share keys or raw traces.

The payment tests include six PostgreSQL tests. To run them, set
`TEST_DATABASE_URL` to a disposable database URL (without surrounding quotes
when pasting at the prompt):

```powershell
$env:TEST_DATABASE_URL = Read-Host "Disposable PostgreSQL URL (keep private)"
python -B -m unittest discover -s backend/payments/tests -p test_integrated_postgres.py -v
Remove-Item Env:TEST_DATABASE_URL
```

These tests create and drop only their uniquely named schemas. Two exercise
the mounted B4 host with the actual OpenRouter HTTP adapter and simulated
provider responses: quote through authorization, and model errors/no-deal
without payment. The agent boundary runs inline in these tests; the domain's
separate process tests verify worker termination/timeouts. They never contact
OpenRouter or PayPal. Skips do not satisfy the database check.

## Deploy and collect evidence

1. Deploy the reviewed commit with the existing frontend build command in
   `render.yaml`. It embeds only the public PayPal client ID and selects API
   mode. Record the deployed commit.
2. Confirm logs contain `B4 negotiation configured: provider=openrouter` with
   the expected model and timeout, then `B2 domain and payment migrations
   completed.` The first line validates configuration only, not provider access.
3. If the team database still has neither demo batch, coordinate the seed using
   `B4_SEED_SCENARIO=split` and `B4_ACKNOWLEDGE_SYNTHETIC_STOCK=true`. Confirm the
   seed log, then remove both variables. Existing conflicting stock requires
   investigation; never reset shared stock or active claims to force a test.
4. After migrations succeed, set `B2_RUN_MIGRATIONS=false`. Keep B4 enabled for
   the acceptance run. `/health` should return `{"status":"ok"}`; it checks
   the process only.
5. Open `/` in a fresh buyer browser session. Request 30 shirts, at least 12 by
   November 13, all 30 by November 16, budget USD 360, navy and black allowed.
   A real model may negotiate a different valid price from the fixture's
   USD 354. Record the actual negotiation ID, quote ID, price and delivery terms.
6. Approve using a Sandbox personal buyer account distinct from the merchant.
   Record the PayPal order and authorization IDs. Verify the authorization
   amount equals the reserved quote total. Refresh: the same authorization
   should remain visible without another approval.
7. In another session, test an impossible deadline (for example 13 shirts by
   November 13, when at most 12 are available). Expect `no_deal`, no quote and
   no checkout. Capture the negotiation reason and confirm browser Network
   shows no payment-order or authorization request. The isolated tests verify
   zero provider calls. Do not replace shared stock with the shortfall seed.

A timeout, provider error or invalid model action is an incomplete test, not
a no-deal pass. Refresh the negotiation before manually retrying a failed
turn. A payment marked pending/unknown requires the existing B4 reconciliation
procedure; do not begin a replacement checkout. Integrated fulfillment capture
remains B5; B3's test-only capture endpoint stays disabled in B4.

For local hosting, load configuration explicitly:
`python -m uvicorn backend.main:app --env-file .env`.
Build the frontend with `VITE_DEFAULT_MODE=api` and the public
`VITE_PAYPAL_CLIENT_ID` in the build environment; the root `.env` is not
automatically loaded by Vite running in `frontend/`.

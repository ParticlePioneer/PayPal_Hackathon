# AgentNegotiate testing instructions

Use this guide to test the buyer journey, AI negotiation, and PayPal Sandbox checkout. Live mode makes real OpenRouter and PayPal Sandbox requests; inventory and fulfillment are simulated. Fixture mode uses predefined responses and does not demonstrate live provider integration.

## 1. Test the deployed website

Open the demo URL supplied with the project submission in a fresh browser session. Select **Live API mode**, or open the site's root with `?mode=api`. Use a PayPal Sandbox personal buyer account distinct from the merchant account for approval; do not use a real PayPal account.

### Sandbox account credentials and where to use them

The project owner supplied these accounts for Sandbox testing. These are PayPal account login credentials, not REST API credentials.

**Buyer account — use to approve checkout**

- Email: `sb-ghepx53858490@personal.example.com`
- Password: `g/k]5%]P`
- Where to enter them: in the PayPal Sandbox sign-in window opened by the application's PayPal checkout button after a valid quote is available.

Start a negotiation, review the quote, and select the PayPal checkout button. Sign in with the buyer email and password above, then review and approve the Sandbox transaction. Return to AgentNegotiate and verify the authorization result. If the window already has another account signed in, sign out or use a fresh browser session before approving.

**Seller / merchant account — use to inspect merchant-side Sandbox activity**

- Email: `sb-jykds53739486@business.example.com`
- Password: `I*VtSE|9`
- Where to enter them: sign in at [PayPal Sandbox](https://www.sandbox.paypal.com/) in a separate browser profile or session, then inspect the merchant account's transaction activity.

Use the merchant account to review the corresponding Sandbox transaction and its status. The buyer account approves the purchase; the merchant account receives it. An authorization does not by itself mean the funds have been captured. The configured Sandbox REST app must belong to this merchant for its account to show the application's transactions.

**Application configuration — use Sandbox REST app credentials**

Do not put either account email or login password into `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, or `VITE_PAYPAL_CLIENT_ID`. Those settings require the Sandbox REST app's client ID and secret, supplied by the project maintainer from the PayPal Developer Dashboard:

- Root `.env`, `PAYPAL_CLIENT_ID`: the merchant Sandbox REST app's client ID.
- Root `.env`, `PAYPAL_CLIENT_SECRET`: that app's client secret, used only by the backend.
- Frontend build environment, `VITE_PAYPAL_CLIENT_ID`: the same public client ID used by the backend, as shown in section 2.
- Root `.env`, `PAYPAL_BASE_URL`: `https://api-m.sandbox.paypal.com`.

For the deployed demo, testers only enter the buyer login at checkout; the maintainer configures the API credentials on the server and during the frontend build. These Sandbox account credentials are supplied for the test workflow; this document does not verify that the passwords or the configured merchant association are current.

### Successful negotiation and checkout

On a demo database with the `split` stock scenario available:

1. Enter an order for **30 shirts** with a **USD 360 total budget**, including delivery.
2. Require **at least 12 shirts by November 13, 2026**, and the remaining shirts by **November 16, 2026**.
3. Allow **navy and black**, with navy preferred.
4. Start the negotiation and follow the buyer/seller conversation through the available turns.
5. Review the resulting quote: quantity, colors, delivery dates, total, and expiry. The total must fit the buyer's budget and the delivery schedule must satisfy both deadlines.
6. Approve checkout through PayPal Sandbox.
7. Verify that the application displays an authorization and that its amount matches the quote.
8. Refresh the page. The existing negotiation and payment status should remain available without creating another payment.

The reference fixture offers 12 navy shirts on Friday and 18 black shirts on Monday for **USD 354**. A live agent can propose a different valid price; do not require an exact USD 354 result. A cheaper Monday-only offer fails the first deadline and must not qualify.

These are fixed demo business dates. Quote expiry uses real server time. Completed orders and active reservations affect available stock, so repeated successful tests require fresh test inventory prepared by the maintainer.

### Impossible delivery requirement

1. In a separate browser session, request **13 shirts by November 13, 2026** when the seeded stock supplies at most 12 by that date.
2. Complete the negotiation.
3. Expect an explanation that the delivery requirement cannot be met, with **no valid quote and no enabled checkout**.
4. Check browser developer tools under Network: the no-deal flow must not create a payment order or send an authorization request.

A model timeout or provider error is an incomplete run, not a successful no-deal result.

### Additional browser checks

| Check | Expected behavior |
| --- | --- |
| Cancel PayPal approval | No successful authorization is displayed for the cancelled attempt. |
| Refresh during negotiation | The saved conversation and current state are restored. |
| Refresh after authorization | The same payment result is restored without a new authorization. |
| Expired quote | Checkout cannot authorize against the expired quote. |
| Repeated click or retry | No duplicate turn or logical payment operation is created. |
| Different browser session | Another buyer's quote cannot be used for checkout. |
| Provider timeout | An error or incomplete state is shown; no fabricated agreement or payment success appears. |
| Narrow viewport and keyboard | Requirements, conversation, quote, and checkout remain usable. |

For a pending or unknown payment result, inspect the existing payment status and use the documented merchant reconciliation procedure. Do not start a replacement checkout to bypass it.

## 2. Local setup

Commands below use **PowerShell**, starting from the repository root. Install Python 3.10+, Node.js 20.19+ or 22.12+, and PostgreSQL for database-backed tests and live checkout.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/domain/requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

For live local testing, fill in the root `.env` with your test database URL, a random session secret of at least 32 characters, your OpenRouter key, and PayPal Sandbox app credentials. Keep secrets out of committed files and screenshots.

Use these settings for the integrated demo:

```dotenv
B4_ENABLED=true
OPENROUTER_MODEL=dots-studio/dots-3-note-preview:free
OPENROUTER_TIMEOUT_MS=30000
OPENROUTER_MAX_OUTPUT_TOKENS=4096
MERCHANT_MINIMUM_TOTAL_CENTS=30000
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
B2_HARNESS_ENABLED=false
B3_CAPTURE_ENABLED=false
B3_ALLOW_FAULT_INJECTION=false
B5_CAPTURE_ENABLED=false
B5_ALLOW_FAULT_INJECTION=false
```

The model above is the repository's configured default. Model availability must be confirmed by the live smoke check. This guide does not change your configuration automatically.

### Prepare a fresh local demo database

Point `DATABASE_URL` at a **disposable test database**. For its initial startup, set these additional values in `.env`:

```dotenv
B2_RUN_MIGRATIONS=true
B4_SEED_SCENARIO=split
B4_ACKNOWLEDGE_SYNTHETIC_STOCK=true
```

Startup applies domain migrations before payment migrations and seeds the simulated split-delivery stock. After successful initialization, set `B2_RUN_MIGRATIONS=false` and remove the two seed settings before subsequent starts. Do not switch seed scenarios or clear active reservations on a shared database.

### Build and serve the integrated application

Vite does not automatically load the root `.env` when building from `frontend/`. Supply the public PayPal Sandbox client ID explicitly:

```powershell
$env:VITE_DEFAULT_MODE = "api"
$env:VITE_PAYPAL_CLIENT_ID = Read-Host "PayPal Sandbox public client ID"
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/?mode=api` and follow section 1. The `/health` endpoint should return `{"status":"ok"}`; this checks the web process, not database, AI, or payment connectivity. Only the PayPal client ID belongs in the frontend build; client secrets and model keys stay server-side.

For an interface-only walkthrough, use `?mode=fixture` and select a fixture scenario. Fixture checkout is simulated.

## 3. Automated checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate fixture
```

Expected: tests pass, installed dependencies are compatible, and the fixture comparison matches the six expected outcomes. The frontend build in section 2 also runs TypeScript checks. There is no separate frontend test script in `package.json`.

Database tests require `TEST_DATABASE_URL` in the process environment; setting `DATABASE_URL` in `.env` alone does not enable them. Use a disposable PostgreSQL database with permission to create and drop test schemas:

```powershell
$env:TEST_DATABASE_URL = Read-Host "Disposable PostgreSQL test database URL"
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
Remove-Item Env:TEST_DATABASE_URL
```

Inspect skips as well as failures. Skipped database tests do not verify stock races, reservations, persistence, or repeat-safe seeding. Automated provider stubs do not establish live OpenRouter or PayPal success.

## 4. Live OpenRouter smoke and six-case evaluation

With `OPENROUTER_API_KEY` configured in the root `.env`:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke --check-config
.\.venv\Scripts\python.exe -B -m backend.domain.model_smoke
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate live --env-file .env
```

The first command validates configuration without a provider request. The second should report `OpenRouter smoke passed`, demonstrating one parsed model action. The evaluation runs up to six turns per case, with a 30-second turn deadline and a 180-second case deadline, and reports accepted conversations plus attempted actions or errors.

| Evaluation case | Expected outcome |
| --- | --- |
| Feasible split | Agreement meeting the quantity, budget, colors, and delivery constraints. |
| Impossible deadline | No eligible agreement. |
| Budget shortfall | No eligible agreement within both parties' limits. |
| Forbidden color | No agreement using disallowed colors. |
| Depleted stock | No eligible agreement using unavailable stock. |
| Ordinary order | Agreement satisfying the straightforward order. |

This evaluation runs in memory: it does not reserve stock, issue persistent quotes, or create payments. The depleted-stock snapshot does not replace the PostgreSQL concurrent-buyer tests.

HTTP 200 alone is not a pass. The response must contain a usable action, pass server validation, and produce the expected case outcome. Record timeouts, provider errors, and incomplete cases separately. Do not combine successful cases from different configurations into a single passing run.

For optional local HTTP diagnostics:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate live --env-file .env --response-trace openrouter-response-local.jsonl
```

The trace filename is gitignored. Raw provider bodies may contain private inputs or reasoning; review before sharing. A timed-out request may have no HTTP response to save.

## 5. Record test evidence

For each run, record the commit (`git rev-parse HEAD`), environment, model ID and limits, initial stock, expected result, observed result, and pass/fail/incomplete status. For integrated checkout, also record the negotiation ID, quote ID, agreed total, PayPal order ID, and authorization ID. Authorization is distinct from capture.

These instructions describe how to test; they do not assert that a new run has passed. The team has reported successful deployment and real-time checks; earlier workspace results and their limitations are preserved in the release handoff.

Further details:

- [OpenRouter configuration](backend/domain/OPENROUTER.md)
- [Domain release handoff and seed behavior](backend/domain/A6_RELEASE.md)
- [Integrated deployment and Sandbox acceptance](backend/payments/B4_DEPLOYMENT.md)
- [Merchant capture and reconciliation rehearsal](backend/payments/B5_REHEARSAL.md)
- [QA overview](qa/README.md)

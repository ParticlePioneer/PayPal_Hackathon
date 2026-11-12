# Payments workstream ? member B

## B1 local checks

The quote adapter is an in-memory, **test-only** substitute. It does not reserve real inventory, persist data, or call PayPal, and is not mounted as an API. Run from the repository root:

```sh
python -m backend.payments.quote_harness
python -m backend.payments.quote_harness --scenario expired
python -m backend.payments.quote_harness --scenario conflict
python -m unittest discover -s backend/payments/tests -v
```

For the real Sandbox OAuth smoke check, obtain a Sandbox REST app client ID and secret from the [PayPal developer dashboard](https://developer.paypal.com/dashboard/). Put them in the process environment as `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`, then run:

```sh
python -m backend.payments.sandbox_auth
```

The command contacts only the PayPal Sandbox OAuth endpoint and does not print tokens or credentials. The application does not automatically load `.env`; configure environment variables in your shell or deployment environment. Keep the secret server-side. Sandbox buyer and business accounts and their checkout flow still need to be verified during B2.

## Database and deployment

`migrations/001_payments.sql` is a PostgreSQL starting schema for recording operation identifiers and outcomes. Apply A's domain migrations first, then apply this file using `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f backend/payments/migrations/001_payments.sql`. Coordinate schema and migration-runner changes with A before integration. This migration has not yet been exercised against PostgreSQL and does not itself implement idempotent payment processing.

The root `render.yaml` describes a FastAPI web service and PostgreSQL database. Connect the GitHub repository to Render and create a Blueprint from it; provide the Sandbox credentials and model key as prompted. Check `/health` on the resulting service URL. Provisioning can incur hosting charges; review Render's selected plans before confirming. The health endpoint checks the web process only, not database or provider connectivity. The Blueprint does not run migrations automatically.

B2?B6 still need actual payment endpoints, checkout, persistence integration, reconciliation and deployment verification. Follow the interfaces and release gates in `implementation_plan.md`.

## Verify deployed dependencies

After deploying this code, in the Render web service's Environment page set `RUN_B1_CHECKS` to `true` and save and redeploy. Open the service's Logs page and look for `B1 database check PASSED (SELECT 1).` and `B1 PayPal Sandbox OAuth check PASSED.` The checks run once in a background thread at startup; they do not expose an HTTP endpoint or print credentials. A FAILED message is deliberately generic. After collecting the results, remove the variable or set it to `false` and redeploy. `/health` remains a process-only check. These checks do not apply or validate migrations.

## B2 Sandbox checkout harness

The test harness is disabled by default and uses a simulated USD 1 quote; it does not reserve inventory and is not integrated with the domain quote adapter. No capture is implemented. Only use Sandbox credentials. The test creates real Sandbox authorizations, not real-money payments.

To run on Render, deploy this revision and set `B2_RUN_MIGRATIONS=true` and `B2_HARNESS_ENABLED=true` on the web service, then redeploy. Startup applies domain migrations followed by payment migrations, transactionally within each migration set and with checksums. Confirm the log says `B2 domain and payment migrations completed.` If migration fails, startup fails without logging database credentials. This modifies the configured database; coordinate with the team before running it.

Open `/test-checkout` in a fresh browser session. Approve using a Sandbox personal buyer account and confirm the page displays an authorization ID. Test cancellation in another fresh browser session. Refresh the first session to check that the authorization is restored. After testing, remove both B2 environment variables or set them to false and redeploy. The test page is publicly accessible while enabled; it is intended for temporary Sandbox testing only.

For a local installation, set environment variables in the process and run domain migrations with `python -m backend.domain.migrate` followed by payment migrations with `python -m backend.payments.migrate`; the application does not automatically read `.env`. Alternatively the startup migration flag above runs both. Never share database URLs or secrets. Unit/API tests: `python -m unittest discover -s backend/payments/tests -v` (requires `httpx`).

The harness does not integrate Member A's persistent quote claims. An uncertain operation must remain pending and must not be replaced with a new quote. The limited B3 recovery procedure below and domain integration need end-to-end testing before release.

## B3 Sandbox capture and reconciliation

The merchant API is restricted to the Sandbox harness. Enable `B2_HARNESS_ENABLED=true` and `B3_CAPTURE_ENABLED=true`, and configure a high-entropy secret of at least 32 characters as `B3_MERCHANT_TOKEN` in the server environment. Requests must include `Authorization: Bearer <merchant token>`; never place the token in the browser or commit it. When finished, disable both flags and remove the token.

After simulated fulfillment, POST `/api/merchant/payments/authorizations/{authorization_id}/capture`. The server looks up the authorization and its saved amount; it does not take an amount from the caller. An uncertain capture can be retried using the same endpoint and same authorization ID within one hour. A PostgreSQL advisory lock and a durable operation ID serialize concurrent captures. Older uncertain operations require manual reconciliation; never create a new quote to work around an unknown result. Completed captures are returned again without a second provider request.

To test a lost response, additionally set `B3_ALLOW_FAULT_INJECTION=true`, then send `X-B3-Simulate-Lost-Response: true` on the first capture request. PayPal processes the Sandbox capture, but the server discards the response and returns 503. Retry without that header using the same authorization ID; the existing PayPal request ID is reused and the capture ID should be returned. Disable the fault injection flag after testing.

For an uncertain order or authorization, the merchant can POST `/api/merchant/payments/quotes/{quote_id}/reconcile/{order|authorize}`. This reuses the persisted provider request ID; it is blocked for the first minute and after one hour. The buyer-facing status endpoint includes the capture ID. This is a test-only implementation; connecting real merchant fulfillment, durable domain claims, authorization/reconciliation state and access controls remains B4 work.

## B4 integration under development

`B4_ENABLED=true` enables the integrated negotiation routes and quote-backed checkout. It requires `SESSION_SECRET`, `DATABASE_URL`, `OPENROUTER_API_KEY`, and an explicitly configured `MERCHANT_MINIMUM_TOTAL_CENTS`. `OPENROUTER_MODEL` defaults to the free Dots model; see [OpenRouter setup](../domain/OPENROUTER.md). The example 30000-cent floor is a simulated demo policy, not a real merchant commitment. Set `B4_MERCHANT_TOKEN` to a separate random secret of at least 32 characters to enable merchant reconciliation. B4 reconciliation reuses the persisted request ID and the domain claim; operations less than one minute old or more than one hour old are not automatically retried. Do not use B3's test-only recovery against integrated payments.

The frontend is built by Render with the public PayPal client ID and live API mode. Domain migrations must be applied before payment migrations. Stock seeding is a separate, explicit operation; never reset or switch fixture stock on a shared database. The integrated code has not yet passed a live database, model, and Sandbox end-to-end test. Keep B4 disabled until those checks pass.

For the isolated database check, set `TEST_DATABASE_URL` to a **disposable** PostgreSQL database using an account that can create and drop schemas. Run `python -m unittest discover -s backend/payments/tests -v`. The test creates and deletes a uniquely named `b4_test_...` schema; without the variable it is skipped. Never put a database URL in chat or source control.

For a coordinated demo deployment only, `B4_SEED_SCENARIO=split` and `B4_ACKNOWLEDGE_SYNTHETIC_STOCK=true` explicitly seed the two simulated batches at startup after migrations. The seed is repeat-safe and refuses conflicting existing batch metadata; it does not clear, replace, or release stock. Remove both variables after successful seeding. The `shortfall` fixture uses the same IDs with different quantities and must use a separate clean database or schema. Never seed a shared database without coordinating with its owner.

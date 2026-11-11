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

This harness does not yet reconcile unknown provider outcomes, recover in-progress work after an interrupted database write, or integrate Member A's persistent quote claims. An uncertain operation must remain pending and must not be replaced with a new quote. B3/B4 must complete reconciliation and domain integration before release.

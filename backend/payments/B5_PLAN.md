# B5 implementation and verification plan

Status: implementation in progress; not ready for deployment. Baseline: `c9f1807` (local main at planning).
Owner: Member B. Scope follows B5 in `implementation_plan.md`.

## Starting evidence and gaps

User-reported B4 evidence from the deployed browser:

- Negotiation `n_6c24840c16f44401a755425bfdd816b2` produced quote
  `q_ffba7e4421b64d5a957c97dcfb0802d5` for USD 360.00, 12 navy by
  2026-11-13 and 18 black by 2026-11-16.
- Order `29F20599HW113690F`, authorization `62869005YB9251511`; refresh
  preserved authorization. Capture has not been reported for this order.
- Negotiation `n_bbcc872dee1b458d8ca25fe5bfdf2a5f` returned `no_deal`,
  `quote: null`, a 12-shirt Friday shortfall, disabled checkout and no payment
  POST reported. Exact submitted requirements were not captured in chat;
  retain this as the observed run, not proof of the 20-shirt preset scenario.
- Six isolated PostgreSQL integration tests passed in the user's environment.
  Their provider responses are simulated, not live PayPal/OpenRouter evidence.

Current implementation gaps:

- `capture.py` implements harness-only capture and returns 404 in B4 mode.
- There is no durable merchant confirmation of simulated fulfillment.
- Initial payment submission and reconciliation use different locking paths.
- The authorization ID is returned to the caller only after domain allocation;
  an allocation/storage failure after provider success can lose that ID locally.
- `provider.py` has POST calls only; recovery cannot currently inspect provider
  state through GET. Unknown outcomes are conservatively kept held.
- Restart recovery, stale approval and integrated capture still need dedicated
  tests and deployed evidence. Some domain release notes still describe Gemini
  and pre-B4 mounting; coordinate current release documentation with Member A.

## Sequence

### 1. Make payment recovery consistent

Files: `integrated.py`, `domain_handoff.py`, `provider.py`, associated tests.

- Serialize initial submission and reconciliation for the same logical operation
  using the same lock strategy. Persist request ID and immutable request details
  before contacting PayPal; keep transactions/lock ordering safe across domain
  adapter connections. A waiting duplicate must not send a concurrent request.
- Persist a verified authorization ID before finishing allocation. Mark the
  payment succeeded only after the required domain allocation is committed.
- Add sanitized, Sandbox-only provider reads for known orders, authorizations
  and captures. Check IDs/relationships, amount, currency and provider status
  before accepting recovered success; never trust a caller-supplied outcome.
- If success is already verified, retry only the missing local allocation/save.
  If provider outcome is unknown, inspect known resources and use bounded replay
  of the original request only when appropriate. Keep the existing conservative
  one-hour replay ceiling unless endpoint documentation justifies a change.
- Provider read failure or missing evidence leaves the operation unknown. Never
  release stock merely because a request timed out or an ID is not yet visible.
  Only a verified terminal non-authorization may release a pending claim once;
  ambiguous/manual cases stay held and are documented. Committed allocations
  are never restored by authorization recovery.

Pass: duplicate/concurrent calls and recovery reuse one operation/request ID;
crashes around provider success, allocation and final persistence recover without
double allocation or loss of held stock.

### 2. Add merchant-confirmed fulfillment and integrated capture

Files: new integrated capture module, `capture.py` routing, an additive payment
migration (do not edit applied migrations), configuration and tests.

- Reuse the server-only `B4_MERCHANT_TOKEN` for integrated merchant actions;
  require `B4_ENABLED=true` and a new `B5_CAPTURE_ENABLED=true` flag for capture.
  B3 harness flags do not enable integrated capture.
- Proposed fulfillment endpoint:
  `POST /api/merchant/payments/authorizations/{authorization_id}/fulfillment`.
  Require explicit acknowledgement that fulfillment is simulated. Persist one
  idempotent confirmation with a server timestamp linked to the verified
  authorization/allocated quote. Never infer fulfillment from authorization.
- Route the existing merchant capture URL to the integrated handler in B4:
  `POST /api/merchant/payments/authorizations/{authorization_id}/capture`.
  Require successful integrated authorization, committed allocation, and the
  saved fulfillment confirmation. Harness authorizations cannot qualify.
- Capture the stored full USD amount once; callers cannot select amount,
  session, quote terms or provider request ID. Partial captures, refunds,
  reauthorization and production-money payments are outside B5 scope.
- Store a capture operation before the provider call. Validate returned capture
  ID, status, amount and currency. Only verified `COMPLETED` becomes captured;
  other outcomes remain unresolved until verified. Repeats return the stored
  capture ID, including after restart.
- Keep the existing buyer status endpoint and CheckoutSlot capture display;
  change frontend only if regression checks identify a gap. Merchant secrets
  and fulfillment/capture controls stay out of the buyer UI.

Pass: no capture without merchant authentication and fulfillment; exactly one
matching capture with persistent buyer-visible status.

### 3. Exercise failures against disposable PostgreSQL

- Stale/expired quote before order and between order creation and approval:
  no authorization provider call; reservation recovery happens once.
- Duplicate approval, concurrent capture, capture versus reconciliation:
  one logical operation and at most one active provider submission.
- Lost provider response, failure saving success, and failure committing domain
  allocation: preserve IDs and stock; recover the original operation.
- Close/recreate the application (and process where appropriate) with pending,
  authorized and captured records: no state depends on Python memory.
- Foreign browser cannot read or act on another buyer's negotiation, quote,
  order or authorization. Missing/wrong merchant token makes no provider call.
- Incorrect provider amount/currency, malformed response, non-completed capture,
  and an operation outside replay limits: no false success or fresh payment.
- Fulfillment/capture guard rejects harness records and unallocated quotes.
- New migration applies after domain migrations and reruns without changes.

Run focused unit/API checks, disposable database tests and frontend build.
Simulated provider tests are recorded separately from live acceptance.

### 4. Rehearse on the deployed Sandbox build

- Prepare a fresh B5 demo database or coordinate append-only demo stock with A
  before creating another quote. B4's successful authorization allocated the
  original stock; repeating the existing seed does not replenish it. Preserve
  B4 records and never clear pending claims to make room for a test.
- Deploy reviewed code, apply the new migration, verify the configured OpenRouter
  model and keep B2/B3 harness/fault flags off. Generate the merchant token on
  the server/operator side; never share it in evidence.
- Complete a fresh real negotiation and buyer-approved authorization. Record
  actual total and IDs; neither USD 354 nor USD 360 is a forced outcome.
- Confirm simulated fulfillment as merchant, then capture. For the one capture
  rehearsal, an explicitly enabled Sandbox-only B5 fault flag/header can discard
  the provider's successful response; retry/reconcile the same operation without
  the header and verify the original capture ID. The hook is disabled by default,
  merchant-only and never accepted through the buyer approval path.
- Repeat capture normally, refresh the original buyer browser, restart/redeploy,
  then refresh again. Confirm one matching completed Sandbox capture and the
  same saved ID throughout. Preserve screenshots and sanitized responses.
- Disable the fault flag immediately after the exercise. Leave capture disabled
  outside the coordinated merchant rehearsal unless the team needs it enabled.
- Do not capture the earlier B4 authorization automatically during this work.
  It is retained as B4 evidence; the plan's pass gate uses a fresh transaction.

### 5. Rehearse clean installation and prepare the release candidate

- Use an isolated checkout/environment and fresh database to install declared
  dependencies, build assets, apply domain then payment migrations, and seed
  explicitly simulated stock. Keep the exact tested model ID and configuration.
- Verify health, UI, real model negotiation, checkout and persisted status with
  clean-install evidence; tests alone do not prove deployment readiness.
- Update Member B's runbook and evidence record; coordinate stale domain release
  notes with A and the final acceptance/README pack with D.
- Record commit, test commands/results, migration result, model ID, URL,
  negotiation/quote/order/authorization/capture IDs and matching amount.
  Include negative-test and restart evidence, known limits and local fallback.
- Tag the verified release candidate only after the checks pass. A passing B4
  commit remains a fallback; any new migration must remain compatible with it.

## B5 completion gate

One real Sandbox capture on a fresh integrated authorization after explicitly
simulated fulfillment; zero duplicate financial operations or allocations;
no cross-session access; stale quotes cannot authorize; uncertain outcomes hold
stock and recover idempotently; startup/refresh restore persisted state; clean
setup and a tagged, reproducible release candidate are documented for Member D.

## Provider references checked while planning

- [PayPal idempotency](https://developer.paypal.com/api/rest/reference/idempotency/):
  replay uses the original request ID within the API's retention period;
  simultaneous requests with that ID may fail, so local serialization is needed.
- [Payments v2](https://developer.paypal.com/api/payments/v2): provider reads for
  authorization/capture and capture of an authorization are separate operations.
- [Authorize and delay capture](https://developer.paypal.com/checkout/delay-capture/):
  capture follows fulfillment; an authorization does not itself prove capture.

# B5 acceptance evidence — in progress

This record distinguishes user-reported deployed Sandbox observations from
local tests using simulated providers. It is not a release signoff.

## Deployed Sandbox observations

- Service: `https://agentnegotiate.onrender.com`.
- B5 code/migration deployment reported as commit `1bf1e29`; logs show
  domain and payment migrations completed and the application started.
- The user reported a fresh live negotiation and PayPal authorization:
  quote `q_514b6ecd3a214ef38734b3edb40ca7a3`, USD 360.00; order
  `91Y352383R4088029`; authorization `4BD82429NW283133F`.
- Capture before fulfillment returned HTTP 409. Explicit simulated
  fulfillment returned `fulfilled`, `simulated=true`.
- With the B5 fault flag enabled, the first capture returned HTTP 503.
  Two subsequent requests returned the same capture ID,
  `5CU10337SD397330B`. User reported one completed USD 360 capture in
  Sandbox, and the buyer page still showed that ID after the fault flag was
  disabled and the service redeployed.
- A separate browser session received `not_found` when reading that quote's
  payment status. The B4 no-deal browser run reported no payment POST requests.
- User reported `B5_ALLOW_FAULT_INJECTION=false` after testing. Verify the
  current `B5_CAPTURE_ENABLED` and migration flags on the running service.

## Automated evidence

- User ran the original nine isolated PostgreSQL integration tests: `OK`.
- After the reconciliation change, the user ran the two saved-authorization
  recovery tests: `OK`. These use a disposable schema and simulated providers.
- User ran `test_expired_quote_blocks_approval_and_new_order_without_provider_calls`:
  `OK`. It was committed in `a4db247` and simulates domain time and provider responses.
- Local backend suite before the latest test-only change: 552 passed, 72 skipped.
  Skips included database-dependent cases; do not count them as passed.
  An isolated local checkout of `a4db247` installed declared backend dependencies,
  ran payment tests (48 passed, 11 skipped), completed `npm ci` and built the
  frontend without live PayPal configuration. Its health check returned OK.
- A disposable database check against the clean checkout reported 2 domain and
  3 payment migrations, 2 seeded batches, zero changes on repeat, and successful
  removal of its uniquely named test schema. The check utility was copied into
  that checkout for the run and must be committed separately.
- The clean Render build reported in chat was from an earlier deployment;
  record the final candidate build separately.

## Outstanding release work

- Commit the clean-install check and updated evidence; identify the final
  candidate commit and ensure it is the one deployed for release.
- Reconfirm the final release configuration and deployed build, including the
  frontend built in API mode with the public Sandbox client ID.
- Record enabled flags and model ID, ensure temporary fault and migration flags
  are off, and give Member D this evidence plus the known limitations.
- Tag a release candidate only after the above checks and the team's acceptance
  process pass. Obtain independent D acceptance and release owner signoff.

OpenRouter provider errors may interrupt a negotiation; retries are not a
guaranteed deal. An uncertain payment requires reconciliation using the
original operation; the code keeps pending claims held. The capture replay is
bounded to one hour; older unresolved outcomes require manual investigation.
Inventory, fulfillment and the 30000-cent merchant floor are synthetic demo
data, not a real merchant commitment. No claim is made about live production
payments or real shipment.

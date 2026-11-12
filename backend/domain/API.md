# A4 negotiation API and handoff

The domain router is importable through `backend.domain.api.create_router`.
The integrated host mounts it when `B4_ENABLED=true`; alternatively a host constructs
`NegotiationService(quote_adapter, seller_factory, agent_source)` and mounts
`create_router(service)` in its own FastAPI application. The service and A3
adapter must use the same configured PostgreSQL database. Install
`backend/domain/requirements.txt` as well as the host's dependencies; apply
domain migrations before payment migrations. The A4 migration adds
`domain_negotiations` without changing the original A3 migration.

The default session dependency requires trusted host middleware to set
`request.state.session_id`. It returns 401 when absent. The host must use the
same secure server-owned session identity for domain and payment operations.
Never obtain this value from a caller-controlled request body or header. A host
may inject another trusted dependency with `session_dependency=...`.

The seller factory receives validated buyer requirements and must return a
trusted `SellerPrivateInput` with merchant policy and optional offer options.
The service replaces its stock batches with current A3 availability. There is
no default seller floor. `agent_source` must supply `generate_buyer` and
`generate_seller`; construct `OpenRouterActionClient(Settings.from_environment(...))`
for a live deployment. See [OPENROUTER.md](OPENROUTER.md).
The synthetic fixture agents are exclusively for clearly labeled testing.

## HTTP contract

`POST /api/negotiations` accepts the documented fields, for example:

```json
{"sku":"shirts","quantity":30,"minimum_by_date":[{"date":"2026-11-13","qty":12},{"date":"2026-11-16","qty":30}],"budget_cents":36000,"allowed_colors":["navy","black"],"preferred_color":"navy"}
```

`minimum_by_date` remains a cumulative list: the second quantity covers all
30 shirts, including the first 12. `POST /api/negotiations/{id}/turn` accepts
`{"expected_version":0}` (then 1, 2, etc.). `GET /api/negotiations/{id}`
restores the current view. Every successful response uses the H0 shape:

```json
{"id":"n_example","version":3,"status":"quoted","messages":[{"actor":"buyer","text":"Can you provide delivery options?"}],"reason":null,"quote":{"id":"q_example","currency":"USD","total_cents":35400,"expires_at":"2026-11-12T18:15:00Z","lines":[{"color":"navy","qty":12,"deliver_by":"2026-11-13"},{"color":"black","qty":18,"deliver_by":"2026-11-16"}]}}
```

The quoted example illustrates the response shape, not a saved live model run.
Responses can instead be `negotiating`, `no_deal`, `expired`, or
`retryable_error`, with `quote: null`. Validation errors return sanitized 422;
stale versions and stock/state conflicts use 409; foreign IDs use 404; expired
claims use 410. A lost turn response should be resolved with GET before retrying.

Private budget, seller policy and stock snapshots are stored server-side in
PostgreSQL, never returned in public views. Only the current role's private
input is passed to its model process. Public messages are rendered from validated
structured events. Restrict database access and retention appropriately.

## Concurrency and recovery

Each turn validates one bounded agent action, then conditionally saves it at
the supplied version. Concurrent duplicate requests can invoke the model more
than once but only one saves an action; others get 409. Never treat a model
call itself as the saved action. The six-turn cap is on saved actions.

An accepted agreement is persisted before quote issuance. Quote issuance uses
the negotiation ID as an idempotency key, then records the quote reference.
If the process fails between those steps, GET retries issuance and recovers the
same reservation. A stock conflict ends the negotiation without a quote; the
buyer may start again. Expired unclaimed quotes are recovered on read or claim.
Pending payment claims remain held until Member B reconciles them; see
[PERSISTENCE.md](PERSISTENCE.md) for cancellation and adapter semantics.

## Local synthetic terminal check

Set `TEST_DATABASE_URL` to a disposable PostgreSQL database whose test account
can create schemas. These commands create and remove only their own randomly
named schemas. They use fixture agents and synthetic 30000-cent seller policy;
they make no Gemini or PayPal calls and do not connect to `DATABASE_URL`.

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.api_demo --scenario split
.\.venv\Scripts\python.exe -B -m backend.domain.api_demo --scenario shortfall
```

The split scenario returns a reserved quote for 35400 cents; the shortfall
scenario returns no quote and explains the four-shirt shortfall. These use an
in-process HTTP test client and real PostgreSQL, not a deployed network server.
The A1/A2 live-model gates and A/B payment integration remain separate checks.

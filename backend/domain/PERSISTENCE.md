# A3 inventory and quotes

This domain module uses actual PostgreSQL transactions. It makes no Gemini or
PayPal requests. It accepts a server-owned A2 result and scenario, verifies the
accepted proposal against buyer requirements and seller policy, then reserves
dated stock atomically. An A2 agreement alone remains a read-only result with
no quote. The model cannot assign a quote ID, expiry, or stock reservation.

## Setup and migration

Use the project virtual environment and `backend/domain/requirements.txt`.
A3 adds `psycopg[binary]>=3.2,<4`. Shared backend requirements are unchanged;
Member B must include domain dependencies when integrating deployment.

Set `DATABASE_URL` to an explicit PostgreSQL URL with host and database name.
Do not print it or commit credentials. Process configuration takes precedence
over an explicitly supplied env file, including an empty process value.

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.migrate --env-file .env
```

Alternatively omit `--env-file` to read only process configuration. The runner
applies domain migrations in a transaction with an advisory lock and a checksum
ledger; repeat execution is a no-op. Changed applied migrations are rejected.
Member B runs domain migrations before payment migrations. There is no automatic
startup migration, schema reset, or destructive down migration.

`migrations/001_domain.sql` creates stock batches, quotes, reservation lines and
authorization claims, all prefixed `domain_`. A trigger freezes quote identifiers,
ownership, terms and expiry. Database constraints prevent negative or excess
inventory. The application changes counters only inside locked transactions.

## Server-side adapter

Construct `QuoteAdapter(DomainDatabase.from_environment(...))`. All methods are
synchronous; future async callers must use an appropriate thread boundary.
These are trusted server calls, not public endpoints. Session IDs must come
from the authenticated/server-owned browser session, never a request body.

| Method | Behavior |
|---|---|
| `add_stock_batch(sku, batch)` | Inserts dated stock. An identical repeat does not reset held or allocated quantities. Changed metadata/total for an existing batch conflicts. |
| `inventory_snapshot(sku)` | Returns server-private current free stock; does not disclose it in public messages. |
| `issue_quote(session, outcome, scenario, issuance_id, ttl_seconds=900)` | Requires a validated accepted agreement; freezes terms and reserves every required batch or rolls back everything. |
| `get_quote(session, id)` | Checks ownership; lazily recovers an expired unclaimed quote before returning 410. |
| `claim_for_authorization(session, id, operation_id)` | Atomically checks ownership, live expiry and held inventory, then persists the claim before any provider request. |
| `commit_allocation(operation_id)` | Moves the pending claim's held quantities to allocated exactly once. |
| `release_claim(operation_id)` | Restores a pending claim's quantities exactly once and cancels the quote. |
| `release_quote(session, id)` | Cancels an unclaimed quote only; cannot release claimed or allocated stock. |
| `recover_expired(limit=100)` | Recovers expired unclaimed reservations, skipping rows another worker has locked. |

The four H0 methods retain their documented names and arguments. Their quote
object exposes `id`, `session`, `currency`, `total_cents`, `expires_at`, `lines`
and internal lifecycle `state`. The `session` field is excluded from serialization
and repr. A4 must explicitly project the H0 public quote shape, excluding internal
state. No frontend request or response contract changes are introduced here.

Issuance IDs are globally unique opaque server-generated IDs. An issuance retry
returns the same quote and original expiry; changing its owner or terms fails.
TTL is an integer from 1 through 3600 seconds, default 900, measured by real
database UTC time after obtaining allocation locks. Business delivery dates stay
fixed fixture dates. Integers persisted to PostgreSQL must fit signed BIGINT.

Claims use globally unique operation IDs, with at most one pending operation per
quote. Retrying that operation returns its existing claim, including after quote
expiry. Reusing an operation for another quote or claiming with another operation
conflicts. Repeated commit/release is safe; release after commit never restocks
allocated inventory, and commit after release conflicts.

**Integration detail for Member B:** release cancels the entire quote; it does
not reopen checkout on that quote. A new negotiation/issuance ID is required.
This differs from the permissive in-memory payment substitute's retry behavior.
Only invoke release after a definitive failure/cancellation known to be safe.
Unknown or pending provider outcomes retain stock, even after TTL, adapter
reconstruction, or process restart. Reconciliation must resolve the same durable
operation. Expiry recovery must never infer a failed payment.

`DomainError` exposes a sanitized `code` and `status_code`: ownership/unknown
resources 404, expiry 410, stock/idempotency/state conflicts 409, invalid input
422, storage failure 503. B's integration must map these explicitly to its payment
error handling; no B-owned code is modified in A3. Raw database exceptions and
connection URLs are not returned by adapter transactions.

## Local verification

Set `TEST_DATABASE_URL` explicitly to a disposable PostgreSQL database. Tests
never fall back to the application's `DATABASE_URL`. Each database test creates
and drops only its own randomly named `a3_test_<uuid>` schema. The test account
therefore needs schema creation privileges. Database tests skip explicitly when
the test URL is absent; a skipped run does not satisfy the A3 database gate.

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_quote_validation.py backend/domain/tests/test_quotes_postgres.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
```

Database checks cover competing buyers, partial-reservation rollback, duplicate
issuance, ownership, frozen terms, expiry while waiting for a lock, concurrent
claims and recovery, commit/release races, repeat-safe seeding and B's migration
following A's. Negotiation inputs in these tests are explicitly synthetic,
including the 30000-cent seller floor. Model outputs are fixture-driven; SQL,
locks, counters, clocks and transactions are real PostgreSQL operations.

For this task the database ran in a dedicated disposable PostgreSQL 18 Docker
container bound only to localhost. No team database was migrated or reset.

## Boundaries and remaining work

A3 provides no HTTP routes, automatic recovery scheduler, persisted negotiation
turns, deployment wiring or payment-provider integration. Call recovery from a
future server task or an explicit maintenance entry point; reads/claims also
recover their own expired unclaimed quotes. Pending claims intentionally need
provider reconciliation to release stock safely.

Real-model A1/A2 gates remain unverified; the prior offline authorization is not
evidence of live negotiation. A3 database evidence cannot establish end-to-end
model, API, frontend or PayPal acceptance. A4 requires separate approval.

# A6 release preparation — signoff pending

The domain implementation can be exercised locally with PostgreSQL and
explicitly synthetic fixtures. **This is not a release signoff.** Gemini 3.6
has passed a live action smoke and a synthetic-policy live negotiation locally;
actual merchant policy and integrated A/B/C checkout are still pending. An A5
live comparison was attempted but is incomplete; its results and the final
release configuration must be recorded against the release commit before
claiming completion.

## Dependencies and application integration

Install both the host and domain requirements into the release environment:

```powershell
.\.venv\Scripts\python.exe -B -m pip install -r backend/requirements.txt -r backend/domain/requirements.txt
```

The existing Render build uses only `backend/requirements.txt`, which does not
declare the domain's `google-genai` or `httpx` requirements. Member B owns
deployment configuration and must include the domain requirements during
integration. The current `backend/main.py` mounts payment routes but does not
mount the A4 router. It must also provide a trusted server-owned session and
seller policy as described in [API.md](API.md). The local virtual environment
contains additional libraries; its passing checks do not prove a clean Render
build or deployed integration.

## Model selection

The user approved `gemini-3.6-flash` as the local configured model. It passed a
real action smoke and completed one live negotiation with synthetic policy; see
[A1_STATUS.md](A1_STATUS.md). The earlier 3.8 and 3.7 requests returned HTTP 504
and 503 respectively. `GEMINI_MODEL` is required explicitly; the domain client
has no automatic fallback. The deployment must explicitly configure the tested
model, and the team must repeat release checks and record A5 live comparison
results against the release commit. Do not label fixture output as live model
evidence or put keys in source control.

## Synthetic stock seed

Use a **disposable test database** with an explicit `DATABASE_URL`. The commands
below apply domain migrations and seed test inventory. Do not point them at a
merchant or shared database without coordinating with its owner.

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.migrate
.\.venv\Scripts\python.exe -B -m backend.domain.seed --scenario split --acknowledge-synthetic
.\.venv\Scripts\python.exe -B -m backend.domain.seed --scenario split --acknowledge-synthetic
```

The `split` seed creates 12 Friday navy and 18 Monday black shirts. `shortfall`
creates eight Friday navy and 18 Monday black shirts. The two scenarios use the
same stock IDs and therefore belong in separate clean test databases when using
the CLI, which targets the default schema. Programmatic callers can use a
`DomainDatabase` configured for a separate schema. Trying to switch a seeded
schema to the other scenario returns a conflict.
The acknowledgement flag is required. The seed writes stock only, never a
seller price floor, and does not make model or payment requests.

The seed checks both batches within one transaction. Repeating identical
seeding inserts no new rows and never updates reservation or allocation
counters, including active claims. Conflicting existing batch data fails rather
than replacing stock. The commands may optionally take `--env-file .env`;
process `DATABASE_URL` takes precedence, even when empty. Never print it.

For a fresh test, provision a **new disposable database or schema**, apply the
migrations, and seed the desired scenario. Coordinate its lifecycle with its
owner. The repository supplies no destructive reset command; do not clear a
shared database or force-release claims to recreate fixture stock. Pending or
unknown payment claims require reconciliation, not expiry-based release.

## Reproducible local checks

Set `TEST_DATABASE_URL` separately to a disposable PostgreSQL database whose
account may create schemas. Tests skip database checks if it is missing; a
skipped run cannot establish the seed or concurrency gates. From the repository
root, using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_seed.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate fixture
.\.venv\Scripts\python.exe -B -m pip check
```

These commands use actual local dependencies and, when configured, actual
PostgreSQL. The comparison uses fixture agents and is labeled synthetic. Test
schemas are unique and removed by the tests; no team database is required.
The A4 terminal examples in [API.md](API.md) also use a disposable database.
Fixed fixture business dates are November 13 and 16, 2026; expiry uses the
database's real UTC clock. Treat fixture dates as a demo clock, not a promise
about live inventory.

## Outstanding release checks

1. Confirm the real merchant's floor and stock and use them as trusted server
   inputs; the synthetic 30000-cent A5 floor is not merchant approval.
2. Verify the configured Gemini model in the release environment with a real
   action, live negotiation and six-case comparison; keep provider failures visible.
3. Member B mounts the domain router and adapter, establishes the shared trusted
   session and payment reconciliation, installs both dependency sets, and runs
   domain migrations before payment migrations.
4. Exercise the final integrated release and repeat-safe seeding on a clean,
   approved test database; record the exact commit and observed results. A live
   payment must never be inferred from a synthetic fixture.

# A6 release handoff

## Owner confirmation — November 12, 2026

The Member A owner confirmed that the remaining work had been checked locally,
that those checks were satisfactory, and that this is the final handoff. This
is an owner-reported confirmation; the specific test output, test environment,
release commit and individual outcomes were not supplied in this conversation.
It does not change the separately recorded results below, including the skipped
PostgreSQL tests and incomplete live comparisons observed in this workspace.

The owner subsequently confirmed that Member B finished B4 and that the full
deployed website and real-time workflow were checked and working. This is an
owner-reported confirmation; deployment URL, commit, and individual Sandbox
transaction evidence were not provided in this conversation.

The domain implementation and integrated OpenRouter host are available for
local testing with explicitly synthetic fixtures. The owner has confirmed the
local handoff above. Independent current-commit PostgreSQL evidence, complete
live-model evaluation, and coordinated integrated Sandbox verification were not
established in this workspace. Actual merchant policy and inventory are not
supplied by the synthetic fixtures.

## Dependencies and application integration

Install both the host and domain requirements into the release environment:

```powershell
.\.venv\Scripts\python.exe -B -m pip install -r backend/requirements.txt -r backend/domain/requirements.txt
```

The Render build installs both requirements files and builds the frontend.
The integrated host mounts the domain router when `B4_ENABLED=true`, with a
server-owned session and an explicit seller floor. See [API.md](API.md) and
[payment integration setup](../payments/README.md). The local virtual
environment's passing checks do not establish a deployed end-to-end flow.

## Model selection

The current live client uses OpenRouter. Its selected model is
`dots-studio/dots-3-note-preview:free`, with 4096 output tokens, 30000 ms per
turn, up to six turns and a 180000 ms evaluation deadline per case. Configuration
and commands are documented in [OPENROUTER.md](OPENROUTER.md). A real buyer
smoke has parsed successfully. Earlier OpenRouter six-case attempts included
timeouts, provider errors and ineligible proposals; do not count an incomplete
case as a pass. Gemini results in older status records are historical, not
evidence for the selected provider. No provider or fixture fallback is automatic.

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

### Current local evidence — November 12, 2026

The code checkout at `c9f1807` was checked with local release-document changes
pending. The backend suite reported **545 passed, 68 skipped**; the skipped
tests include PostgreSQL gates because `TEST_DATABASE_URL` was not configured.
`pip check` and the frontend production build passed. Configuration validation
selected `dots-studio/dots-3-note-preview:free`; it did not itself contact the
provider. A prior actual OpenRouter buyer smoke on the integrated client parsed
an action successfully.

A live in-memory comparison at 30 seconds per turn used synthetic scenarios,
the current OpenRouter client and a 4096-token output limit. The scripted
baseline matched six cases. The live model matched feasible split, budget
shortfall, depleted stock and ordinary order; impossible deadline and forbidden
color timed out and remain incomplete. The split and ordinary agreements were
validated in memory only; no quote, reservation or payment was issued. The
depleted-stock case models a snapshot, not concurrent buyers. Local provider
traces and complete conversations can contain sensitive data and should not be
committed or shared without review.

A separate diagnostic with both the per-turn and provider timeouts raised to
45 seconds matched five cases; impossible deadline timed out on the seller's
second turn. This is not a pass of the six-case live gate, and it did not change
the 30-second release defaults. The 45-second run's forbidden-color result was
no deal at the six-turn limit, with four ineligible proposals. Do not combine
results from the two configurations into a single successful evaluation.

The approved disposable PostgreSQL Docker command failed because the Docker
engine was unavailable. No test database was configured; therefore the current
checkout's A3/A4/A5 database and A6 seed gates remain unverified. Earlier
PostgreSQL evidence in [PERSISTENCE.md](PERSISTENCE.md) is historical and does
not replace this release check.

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

## Checks not independently established in this workspace

The owner has confirmed final local verification and that B4 and the deployed
real-time website were checked and working. The items below preserve the
earlier workspace evidence gaps; they are not a claim that the owner's later
checks failed.

1. Confirm the real merchant's floor and stock and use them as trusted server
   inputs; the synthetic 30000-cent A5 floor is not merchant approval.
2. Verify the configured OpenRouter model in the release environment with a real
   action, live negotiation and complete six-case comparison; keep provider
   failures visible.
3. Coordinate with Member B to verify the integrated host, trusted session,
   payment reconciliation and migration order on the release configuration.
4. Exercise the final integrated release and repeat-safe seeding on a clean,
   approved test database; record the exact commit and observed results. A live
   payment must never be inferred from a synthetic fixture.

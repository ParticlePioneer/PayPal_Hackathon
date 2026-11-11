# A5 reliability and evaluation

A5's offline checks exercise the existing negotiation and quote boundaries. They
do not make Gemini or PayPal calls and do not establish real-model performance.
The A1/A2 live-model gates remain open, and the actual merchant floor is still
needed before merchant-backed checkout. The project checkout used for these
checks can be identified with `git rev-parse HEAD`; no frozen experimental
data or results are read or modified by this evaluation harness.

## Six development scenarios

The comparison constructs synthetic cases in `evaluate.scenarios()`. Both
sources use the same validated scenario, six-turn cap and timing limits.

| Case | Expected result | Synthetic setup |
|---|---|---|
| `feasible_split` | Agreement possible | 12 navy Friday, 18 black Monday, 35400 cents |
| `impossible_deadline` | No deal | Only eight allowed shirts are available by Friday |
| `budget_shortfall` | No deal | Buyer budget 34000 cents, offered split 35400 cents |
| `forbidden_color` | No deal | Buyer accepts navy only; remaining stock is black |
| `competing_buyer_depleted` | No deal | Second buyer sees zero Friday stock after prior allocation |
| `ordinary_order` | Agreement possible | Ten navy shirts, one Monday delivery |

Merchant floors and stock are synthetic test inputs. The competing-buyer case
models an already-depleted snapshot; it is not itself a concurrent race. Actual
competing buyers and expiry/claim races are checked separately against PostgreSQL.
No merchant-backed quote or live payment is created by the comparison.

Run the development comparison from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate fixture
```

The `baseline` is a simple deterministic negotiator; `fixture` is the existing
deterministic fixture-agent substitute. **Both are simulated**, not AI models.
The CLI prints results to stdout and does not persist them. Each case records
expected outcome, completion status, turn count, ineligible proposals, invalid
actions, server-accepted terms and whether a quote was issued. Here
`server_accepted_terms` means A2's constraints accepted the terms; it does not
mean inventory was reserved. `quote_issued` is always false in this runner.
An incomplete candidate or baseline makes the CLI exit nonzero; it is not
counted as a matching result.

The actual spawned-process fixture run on November 12, 2026 matched all six
expected outcomes for both simulated sources: two eligible agreements and four
no-deals each. Each source made one ineligible proposal in the budget-shortfall
case; the server did not accept that proposal. Zero quotes were issued. These
counts are not AI evaluation results and must not be presented as such.

After provider access is restored, an explicitly authorized live comparison can
use `--candidate live` and the desired `--env-file`. It uses the same synthetic
scenarios and records the configured model ID; failures are reported as failures,
with no scripted fallback. Live runs may incur provider usage and may take up to
the configured per-turn limit for each case. Live performance counts remain
pending. A matching outcome in synthetic evaluation does not prove real seller
policy approval or payment integration.

## Reliability evidence and limits

- An actual child process reconnects to PostgreSQL after a pending authorization
  claim has outlived its quote TTL. Expiry recovery leaves the claim and all 30
  reserved shirts intact; a later confirmed commit allocates them once. This
  uses a pending domain claim to simulate an unknown outcome; it does not call or
  prove Member B's payment-provider reconciliation.
- An expired quote is claimed concurrently with expiry recovery. The claim fails
  as expired and the full reservation is restored once. Prior A3 tests also
  cover competing buyers and duplicate release.
- API privacy tests capture the selected role's input and check the public
  response: the buyer does not receive the seller floor or stock batches, the
  seller does not receive the buyer budget, and those fields are not returned
  in the public transcript. Structured public prices are intentionally public;
  no schema can rule out information deliberately encoded in allowed values.
- A real spawned agent process hangs during an API turn. The boundary times out,
  terminates and reaps it, and the API stores no action or quote for that turn.

These are local checks against a disposable database. Router mounting, the host's
trusted session, the integrated payment provider and deployment remain Member B
integration work. Expiry recovery does not release a pending claim automatically;
only a confirmed outcome may resolve it. See [API.md](API.md) and
[PERSISTENCE.md](PERSISTENCE.md).

## Commands

Set `TEST_DATABASE_URL` to a disposable PostgreSQL database whose test account
may create schemas. Database tests skip if it is absent; a skipped run cannot
establish the database acceptance gate. All test schemas have unique test-owned
names and are dropped by their fixtures.

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_evaluate.py backend/domain/tests/test_a5_postgres.py backend/domain/tests/test_a5_api.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
```

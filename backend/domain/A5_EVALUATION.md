# A5 reliability and evaluation

Current live evaluation uses OpenRouter; see [OPENROUTER.md](OPENROUTER.md).
The Gemini runs and commands below are historical and do not describe the current provider.

A5's offline checks exercise the existing negotiation and quote boundaries. They
do not make Gemini or PayPal calls and do not establish real-model performance.
The A1/A2 live-model gates were still open at the time of the offline checks;
later local Gemini 3.6 verification is recorded in [A1_STATUS.md](A1_STATUS.md).
The actual merchant floor is still needed before merchant-backed checkout. The project checkout used for these
checks can be identified with `git rev-parse HEAD`; no frozen experimental
data or results are read or modified by this evaluation harness.

## Six development scenarios

The comparison constructs synthetic cases in `evaluate.scenarios()`. Both
sources use the same validated scenario, six-turn cap and timing limits.

| Case | Expected result | Synthetic setup |
|---|---|---|
| `feasible_split` | Agreement possible | 12 navy Friday, 18 black Monday, 35400 cents |
| `impossible_deadline` | No deal | Only eight allowed shirts are available by Friday |
| `budget_shortfall` | No deal | Buyer budget 29000 cents, synthetic seller floor 30000 cents |
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

To capture live OpenRouter responses for these synthetic cases, run:

```powershell
.\.venv\Scripts\python.exe -B -m backend.domain.evaluate --candidate live --env-file .env --response-trace openrouter-response-live.jsonl
```

The optional JSONL trace appends one record per received provider response, with
the case, role, HTTP status, HTTP version, headers and complete decoded body.
The configured key and selected sensitive headers are redacted. The trace can
still contain sensitive provider or generated content; keep it local and review
it before sharing. Files named `openrouter-response-*.jsonl` are gitignored; other
filenames are not automatically ignored. Use a fresh filename for each run.
No HTTP record exists when a request times out or fails before a response is
received. The parent-enforced turn deadline includes process startup. These are
OpenRouter provider responses, not the application's HTTP endpoint responses.

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
That historical fixture run used the earlier 34000-cent budget and a
30000-cent seller floor. Those limits overlap, so its expected no-deal label
was not valid for a flexible negotiator, despite both scripted sources declining.
The original counts above remain recorded; the current scenario uses a budget
below the seller floor so that its no-deal expectation is justified.

## Initial live comparison and case correction — November 12, 2026

An initial live run used Gemini 3.6 Flash and the earlier 34000-cent budget
case. Three candidate outcomes matched the original labels; two ended with
retryable provider/model errors. In the budget case the agents reached terms
that the server accepted, so the result differed from the original no-deal
label. The original budget and floor allowed an overlap; a deal was therefore
possible. This was a scenario-label error, not evidence that the accepted
agreement violated the buyer budget or seller floor. No quotes were issued.
The case was subsequently corrected to a 29000-cent synthetic budget; results
from the two case versions must not be combined or treated as the same run.

## Corrected live comparison — November 12, 2026

The corrected 29000-cent-budget comparison was run separately with Gemini 3.6
Flash. The scripted baseline matched all six expected outcomes. The live
candidate completed the feasible-split case with a decline, which did not match
the benchmark's target agreement; five other cases ended in retryable model
errors and were not scored as matches or mismatches. No candidate terms were
accepted and no quotes were issued in this run. One candidate proposal in the
feasible case was ineligible under the server's scenario checks. A decline on a
feasible scenario differs from the benchmark target but is not automatically an
invalid action.

After this comparison, a separate minimal request returned HTTP 429
`RESOURCE_EXHAUSTED`. A subsequent sanitized diagnostic indicated a daily
limit and provided a retry delay of 33910 seconds. This is evidence of a quota
limit at diagnostic time; the evaluation's generic model-error results do not
identify the exact cause of each earlier failed call. The live comparison is
incomplete and must be rerun after quota becomes available.

After provider access is restored, an explicitly authorized live comparison can
use `--candidate live` and the desired `--env-file`. It uses the same synthetic
scenarios and records the configured model ID; failures are reported as failures,
with no scripted fallback. Live runs may incur provider usage and may take up to
the configured per-turn limit for each case. Live performance counts remain
pending in full. A matching outcome in synthetic evaluation does not prove real seller
policy approval or payment integration.

## Live response-trace run — November 12, 2026

Using the corrected scenarios and `gemini-3.6-flash`, feasible split,
impossible deadline, depleted stock, and ordinary order matched their expected
outcomes. Budget shortfall and forbidden color were incomplete: Gemini returned
HTTP 503 `UNAVAILABLE` for the seller and buyer respectively, citing high
demand. The baseline matched all six. The runner made no automatic retries and
issued no quotes; a 503 is not evidence of a negotiation result. The local
response trace contains the provider responses for this run.

## Current OpenRouter comparison — November 12, 2026

At code commit `c9f1807`, the configured `dots-studio/dots-3-note-preview:free`
model was compared against the scripted baseline with a 30-second per-turn
limit and 4096 output tokens. The baseline matched six synthetic cases. The live
model matched feasible split, budget shortfall, depleted stock and ordinary
order. Impossible deadline and forbidden color timed out and were incomplete;
neither is counted as a match. No quote was issued. The 30-second boundary
includes process startup and provider time. These are local results, not
deployed or merchant-policy evidence.

A separately executed 45-second diagnostic at the same code commit matched
five cases; impossible deadline timed out on turn two. Forbidden color reached
the six-turn limit with four ineligible proposals and no deal. The baseline
matched all six. This different timeout was diagnostic only, left the release
default unchanged, and does not make either six-case run complete.

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

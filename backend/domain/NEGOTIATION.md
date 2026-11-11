# A2 offline negotiation runner

Offline implementation was explicitly authorized while A1's real-model gate was
still blocked. This document does not declare A1 or A2 live acceptance passed.
No live Gemini request is required to run the mock terminal or tests.

## Boundaries

`negotiation.py` implements a fresh in-memory buyer/seller conversation with all
five action types. The runner creates event and offer IDs and freezes proposed
terms using the existing immutable contracts. These are internal terminal
results, not A4's HTTP public view. No API contract, payment adapter, database
schema, reservation, quote issuance, or payment behavior has been implemented.

A successful result says `agreed`, includes eligible agreement terms, and always
has `quote: null`. Stock is unchanged. Checkout remains unavailable until the
later stock reservation and quote stages pass their own gates.

## Rules

- The buyer starts; turns alternate. The cap is six total model actions, not six
  actions per agent. A lower cap may be configured, never a higher one.
- An initial `offer` is allowed only before there is an active proposal.
- `counter` replaces the current opposite-party proposal. Old IDs become stale.
  A proposer may revise its own active offer in response to the opponent's
  `ask` with topic `revised_offer`; that revision also issues a fresh offer ID.
- `accept` references exactly the active opposite-party proposal; it never
  resubmits terms. A proposal commits its proposer, so a valid opposite-party
  acceptance establishes mutual agreement.
- `ask` does not invalidate a proposal. A `decline` without an ID ends the
  conversation; a targeted decline must reference the active opposite-party
  proposal.
- Malformed actions and invalid references stop safely with no agreement.
- Commercially infeasible proposals can appear in history. Before acceptance,
  the server checks total quantity, allowed colors, inclusive price against both
  private thresholds, every cumulative delivery minimum, and dated stock.
- Stock checks are read-only cumulative checks per color and arrival date. They
  prevent batch reuse across offer lines but provide no concurrency guarantee.
  Atomic reservations belong to A3.
- Budget and floor failures produce the same generic public price issue. They
  never publish either threshold. Deadline/stock explanations can report a
  required shortfall, as the shared fixture requires; raw batch data stays private.

## Timeout and agent boundary

Each agent call runs in a fresh `spawn` process. Only that role's validated
private input and the shared structured events are passed to the child. The
source object is trusted executable code and must not cache opposite-role data;
the provided Gemini client stores only settings, and mock agents are stateless.

Default limits are six turns, 30 seconds per call, and 120 seconds total. Call
timeouts may be 100 through 60000 milliseconds; the overall limit may be 100
through 360000 milliseconds. The remaining overall time bounds each call.
Process startup counts toward the call budget. Local cleanup permits up to two
seconds of additional grace for termination/reaping. Late results are discarded,
and no thread is abandoned. Killing the local worker does not promise remote
provider cancellation.

The worker's stdout/stderr are suppressed. Only bounded JSON actions or known
error codes cross back to the parent. Provider failures are never replaced with
mock outputs. The process boundary also revalidates actions and role inputs.

## Scenario input and seller policy

The CLI requires a private `NegotiationScenario` JSON file containing `buyer`
and `seller`. The server-only scenario holds both parties but is never itself
sent to either model. Reuse the existing `BuyerPrivateInput` and
`SellerPrivateInput` field definitions.

Seller input now has optional `offer_options: list[OfferTerms]`, defaulting to an
empty list. This backward-compatible private field lets the seller know its
merchant-supplied starting offers. It is not added to shared context or the
buyer's private input. A starting option is published only if the agent actually
offers it. Server eligibility checks remain required.

`fixture_scenario(minimum_total_cents, shortfall=False)` constructs the approved
buyer and split-offer facts but requires an explicit floor. There is no default
merchant floor. With `shortfall=True`, Friday navy availability is eight; Monday
black availability remains eighteen. The Monday-only fixture still has no
invented color and is not silently converted into an actionable offer.

For a development demonstration, create **synthetic policy only** under the
ignored domain cache. The value below is a test input, not agreed merchant policy:

```powershell
.\.venv\Scripts\python.exe -B -c "from pathlib import Path; from backend.domain.negotiation_fixtures import fixture_scenario; target=Path('backend/domain/.pytest_cache'); target.mkdir(exist_ok=True); (target/'a2-split-synthetic.json').write_text(fixture_scenario(30000).model_dump_json(),encoding='utf-8'); (target/'a2-shortfall-synthetic.json').write_text(fixture_scenario(30000,shortfall=True).model_dump_json(),encoding='utf-8')"
.\.venv\Scripts\python.exe -B -m backend.domain.negotiate --mode mock --input backend/domain/.pytest_cache/a2-split-synthetic.json
.\.venv\Scripts\python.exe -B -m backend.domain.negotiate --mode mock --input backend/domain/.pytest_cache/a2-shortfall-synthetic.json
```

Every CLI result includes `mode` and `simulated`. Mock mode uses deterministic
fixture agents and never loads model credentials. It demonstrates plumbing and
server validation, not AI behavior. Never use a synthetic policy file as live
merchant configuration. Keep real private inputs in ignored local files.

## Live mode, after A1 and policy verification

The CLI supports the existing Gemini client without changing the model provider:

```powershell
$env:GEMINI_MODEL = 'gemini-3.8-flash'
.\.venv\Scripts\python.exe -B -m backend.domain.negotiate --mode live --input path/to/real-private-scenario.json
```

The scenario must contain an actual team-provided seller floor and inventory
snapshot; the live gate cannot be demonstrated with invented commercial policy.
Live mode has no automatic model fallback or scripted successful outcome.
Successful mock tests do not establish real-model performance. A2's live pass
gate remains pending until a real run finds a qualifying split or gives a genuine
decline trace, with A1's provider smoke independently verified.

Exit 0 means a completed conversation (`agreed` or `no_deal`), not a successful
purchase. Exit 1 means invalid input, model failure, or timeout. Invalid CLI flags
use argparse's exit 2. Private inputs and exceptions are never printed.

## Verification

```powershell
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_negotiation.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend/domain/tests/test_agent_process.py backend/domain/tests/test_negotiate_cli.py -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m pip check
```

These tests cover action/state transitions, malformed/stale/self references,
commercial failures, exact fixture quantities and cents, privacy, turn/time
limits, process cleanup, and real terminal subprocesses. Test-only scripted
agents run in the pure state tests; separate integration tests exercise actual
spawned workers. No provider calls or payment calls are made by these tests.

## Recorded offline verification

November 11, 2026: final backend regression **423 passed, 1 existing warning**
in 47.32 seconds, including 79 new A2 tests. The warning concerns collection of
the payment-owned `TestQuote` dataclass; that file remains untouched. `pip check`
reported no broken requirements. No dependencies were installed for A2.

Both mock commands above were also executed directly and exited 0. The split
run agreed to 35400 cents in three turns with `quote: null`; the shortfall run
declined in two turns, explaining the four-shirt Friday shortfall. These runs
used the explicitly synthetic 30000-cent test floor and are not live AI evidence.
The generated scenario files are ignored by Git. No provider or payment call
was made during this offline implementation task.

After initial local testing, the implementation assistant applied the five
council thinking perspectives directly, without independent reviewers or claimed
approvals. Review findings and dispositions:

- **Contrarian:** stale/self references, malformed responses, and failed provider
  calls must not produce agreements. Negative/no-fallback tests verify this.
- **First Principles Thinker:** a revised-offer question needs a valid response
  path. Added requested self-revision with a new ID, retaining the prohibition
  against accepting one's own offer; regression tests pass.
- **Expansionist:** optional merchant starting offers belong only in seller
  input until offered. Added private `offer_options` with an empty default and
  tests for publication only through an actual action.
- **Outsider:** clearly label simulated output and unreserved agreement. Both
  terminal modes expose their mode, and all results retain `quote: null`.
- **Executor:** rejected falsey invalid limits instead of silently defaulting;
  strengthened timeout integration to prove a running hung agent is terminated
  and reaped. Final backend regressions pass after these corrections.

Offline implementation acceptance passed. Real A1 smoke and A2 live negotiation
acceptance remain pending. No A3 or later work was implemented.

## Follow-up: synthetic versus merchant policy

The A3 domain implementation was subsequently added; the earlier A2-only
statements above describe its original verification. For a development demo,
the existing explicit 30000-cent fixture floor may be used as synthetic seller
policy, clearly labeled as such. Do not present it as the merchant's approved
minimum or silently use it for merchant-backed checkout. A real policy is still
needed before that integration. Live A1 and A2 outcomes remain unverified; the
November 12 smoke attempt returned HTTP 504, as recorded in `A1_STATUS.md`.

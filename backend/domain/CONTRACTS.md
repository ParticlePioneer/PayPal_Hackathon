# A1.1 domain contracts

These contracts define data and validation only. They do not run models, choose
actions, check offer history, authenticate actors, reserve stock, issue quotes,
or expose API routes.

## Local dependencies and checks

From the repository root using the existing Python 3.12 environment:

```powershell
.\.venv\Scripts\python.exe -B -m pip install -r backend/domain/requirements-dev.txt
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider
```

Runtime requirements are in `requirements.txt`; pytest is development-only.
The shared backend requirements and deployment configuration remain unchanged.
Domain dependencies must be installed explicitly until the team agrees on shared
dependency integration. The tested versions are reported with the task results;
these requirement ranges are not a complete reproducibility lockfile.

## Contract usage

- `ACTION_ADAPTER.validate_json(raw_json)` parses the discriminated action union.
  Actions cannot carry actor identities, authoritative IDs, or arbitrary text.
- Every model rejects unexpected fields. Quantities and cents reject strings,
  floats, and booleans. Calendar dates accept Python `date` objects or canonical
  ISO strings; datetimes and numeric timestamps are rejected.
- Models are frozen, collections use tuples, and JSON serializes those tuples
  as arrays. Do not bypass validation with `model_construct` or unvalidated
  `model_copy(update=...)` when processing untrusted data.
- `OfferTerms.validate_quantity(requirements)` explicitly checks aggregate
  quantity. Budget, deadlines, allowed-color eligibility, seller policy, stock,
  and offer-reference state are separate checks for later approved work. A late
  or expensive proposal is not a malformed action.

## Delivery and frontend compatibility

`minimum_by_date` is a cumulative list, preserving the documented field name:

```json
[{"date":"2026-11-13","qty":12},{"date":"2026-11-16","qty":30}]
```

The final quantity includes earlier deliveries. Member C should submit 12 then
30, not 12 then 18. No scalar-date adapter is implemented: a single date cannot
express both deadlines without additional information. Date validation is not
tied to the real wall clock, so fixed business fixtures remain usable.

`BuyerRequirements` contains shareable requirements only. The future create API
must explicitly map its six documented fields to that model plus the private
budget; there is no API endpoint or request adapter in A1.1.

## Privacy and trusted boundaries

Construct `BuyerAgentInput` and `SellerAgentInput` separately. Their `private`
fields intentionally serialize the respective party's private input for that
party's model call; never return or log an entire agent input as a public view.
The seller's budget-free shared context contains no private inventory or floor.

Only trusted server code may create `PublicEvent` metadata after validating an
action. Pydantic checks shape, not provenance, identity, consent, or negotiation
state. `PublicMessage(event=approved_event)` is an output-only renderer: its
serialized shape is exactly `{actor, text}`. It rejects caller-supplied text and
uses fixed templates; opaque references are not interpolated. It cannot parse
historical `{actor, text}` payloads back into events.

No raw model response, prompt, reasoning, or private validation detail belongs in
shared context or public output. String validation errors hide input values, but
`ValidationError.errors()` can still contain them: future API/error handlers
must use approved public codes and never publish raw exceptions. No generic
schema can detect secrets deliberately encoded in otherwise valid public prices
or identifiers; model-context isolation and trusted construction remain needed.
Private-term disclosure is unsupported in A1.1.

## Fixture limits

`buyer_fixture()` and `split_offer_fixture()` encode the approved dates, colors,
quantity, budget, and inclusive split price. `monday_offer_fixture()` records only
the known quantity, inclusive price, and Monday arrival as
`UnallocatedOfferFixture`. It intentionally has no color and cannot validate as
`OfferTerms`. The team must provide a color before using it as an actionable
proposal. No merchant floor or inventory availability is invented. Synthetic
seller values in unit tests are validation examples, not commercial policy.

The fixture SKU `shirts` and the navy/black catalog follow the approved design.
No live-provider success, stock feasibility, reservation, payment, or full A1
completion follows from passing these contract tests.

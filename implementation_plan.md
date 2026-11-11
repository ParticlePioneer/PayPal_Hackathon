# AgentNegotiate implementation plan

**Team:** four developers. **Timebox:** 24 elapsed hours from kickoff. **Release owner:** Member 4. Assign actual names and record the kickoff time before starting. Set H24 to the earlier of kickoff + 24 hours or the official submission cutoff. Target submission at H23. If less time remains, cut the optional work first.

## Four parallel workstreams

| Owner | Codex access assumed | Owns from start to finish | First independent test |
|---|---|---|---|
| A · Member 1 | Yes | AI agents, negotiation API, inventory, quote lifecycle and domain migrations | Negotiate and reserve stock from a terminal |
| B · Member 2 | Yes | PayPal API, payment persistence, PayPal button component, hosting and integration | Authorize a USD 1 sandbox quote in a standalone checkout page |
| C · Member 3 | No | Buyer-facing React screen, frontend state and error handling | Complete the buyer journey in a browser against local fixtures |
| D · Member 4 | No | Acceptance cases, buyer-perspective QA, demo video and submission | Score the sample offers by hand and prepare the recording script |

Assign actual people by experience. Swapping people is fine; keep each workstream intact. Each task below lists its **direct prerequisites**. An em dash means start immediately. The contract and fixtures in this document are available at kickoff. Mock services are for development; the release gates require real AI and PayPal Sandbox. Reviews are evidence checks and do not block independent coding.

## What a judge must be able to do

Enter a bulk order, watch two pretrained AI agents negotiate over price and delivery, inspect a merchant-backed quote, approve it as a PayPal Sandbox buyer and see the resulting authorization. Then try an impossible deadline and see exactly why checkout is unavailable. The inventory and fulfillment are simulated. The model calls and sandbox payment calls are real.

| Shared fixture | Expected result |
|---|---|
| Buyer needs 30 shirts, at least 12 delivered by Fri Nov 13, 2026, remainder by Mon Nov 16, budget USD 360 including delivery. Navy preferred, black allowed. Merchant offers all 30 Monday for USD 330 or 12 navy Friday + 18 black Monday for USD 354. | Monday-only offer fails the first deadline. The split offer qualifies. Merchant reserves both batches. Approved checkout amount is 35400 cents. |
| Same buyer, only 8 deliverable Friday, no other Friday supply | Explain the four-shirt shortfall. No quote, reservation, order or payment. |
| Two buyers compete for the same final 12 Friday shirts | At most one receives a valid reservation. The other receives a stock conflict and may renegotiate. |

Use fixed business dates with a demo clock for scenario comparisons. Use real server UTC timestamps for reservation expiry. The two offers above are test fixtures. The live negotiation should permit different wording and valid action sequences. Never script a successful outcome over a failed model run.

## Handoff contract available at H0

Each owner can copy these examples into their own tests. Use integer USD cents, ISO arrival dates, opaque IDs and a server-owned browser session. Develop in separate directories on short branches. A owns `backend/domain/`, B owns `backend/payments/`, the app entry point, deployment and `frontend/src/CheckoutButton.tsx`, C owns the remaining frontend, D owns `qa/`, README and submission materials. A and B maintain separate migration files; B runs domain migrations then payment migrations on deployment. Integration uses one FastAPI service and one PostgreSQL database.

| Producer → consumer | Fixed interface | Development substitute |
|---|---|---|
| A → C | POST /api/negotiations accepts sku, quantity, minimum_by_date, budget_cents, allowed_colors and preferred_color. POST /api/negotiations/{id}/turn accepts expected_version. GET /api/negotiations/{id} resumes. Each returns the same public view below. | C implements a local adapter returning negotiating, quoted, no_deal, expired and retryable_error views. |
| A → B | Server-side domain adapter provides get_quote(session,id), claim_for_authorization(session,id,operation_id), commit_allocation(operation_id), release_claim(operation_id). All mutations are idempotent. Claim checks ownership, stock and expiry atomically. | B implements a test-only adapter with a seeded USD 1 quote and selectable expiry/conflict. B swaps in A’s adapter at integration. |
| B → C | CheckoutButton takes quoteId and onStatusChange(status). B owns its PayPal JS callbacks. POST /api/payments/orders receives quote_id, POST /api/payments/orders/{id}/authorize handles approval, GET /api/payments/quotes/{id} returns status. Capture is merchant-only. | C renders a local placeholder with the same props. B owns the final component import and integration wiring. |
| A/B/C → D | Browser flow, status labels and evidence IDs. D needs only a URL for acceptance and a tagged commit for reproducibility. | D can write expected outcomes, README scaffold and video storyboard from the fixture at H0. |

Example public view for the quoted state (the UI should render other states when quote is null):

```json
{"id":"n1","version":4,"status":"quoted","messages":[{"actor":"buyer","text":"Can 12 arrive Friday?"}],"reason":null,"quote":{"id":"q1","currency":"USD","total_cents":35400,"expires_at":"2026-11-12T18:15:00Z","lines":[{"color":"navy","qty":12,"deliver_by":"2026-11-13"},{"color":"black","qty":18,"deliver_by":"2026-11-16"}]}}
```

Use fresh UTC expiry timestamps at runtime. An expired fixture is intentional only in the expiry test. HTTP 409 means refresh after a version or stock conflict, 410 means an expired quote, and a provider timeout may leave payment pending. The UI requests the existing status on refresh. The quote server alone supplies monetary terms to the payment server. Public messages exclude buyer budget and seller floor unless the buyer explicitly chooses to disclose a term. If a field must change, its owner supplies a backwards-compatible default or an adapter in the same change.

## A · Member 1 with Codex — negotiation through reserved quote

| ID / window | Direct prerequisites | Subtasks | Deliverable | Pass gate |
|---|---|---|---|---|
| A1 · H0–2 | — | Test model credentials. Define Pydantic actions, separate role inputs, validate fixture dates and cents. | Model smoke command and typed action examples. | Real configured model returns a parseable action. Each role sees only its own private inputs. |
| A2 · H2–5 | A1 | Implement ask, offer, counter, accept and decline. Give agents a six-turn cap and bounded timeout. Compare proposed terms to seller policy and buyer deadlines. | Independent two-agent terminal runner. | Live run finds a qualifying split or gives a reason for declining; malformed responses cannot issue a quote. |
| A3 · H5–8 | A2 | Implement domain migration, dated stock, quote issuance and all-or-nothing reservation. Freeze terms and enforce session ownership. Add authorization-claim adapter and expiry recovery. | Domain module with PostgreSQL race tests and adapter matching the H0 contract. | Two buyers compete for 12 shirts. Exactly one quote reserves them. An unavailable second batch rolls back the first. Repeated release restores stock once. |
| A4 · H8–10 | A3 | Expose domain router, persist each turn using expected_version, seed success and shortfall cases, restore public view after refresh. | Importable router and live quote adapter handed to B; API example for C. | Terminal client completes both scenarios against PostgreSQL. Duplicate turn produces one saved action. Expired/foreign quotes cannot be claimed. |
| A5 · H10–17 | A4 | Exercise timeout, concurrent expiry and authorization, and private-data separation. Compare six labeled scenarios with a scripted negotiator under the same turn limit. | Domain regression results and AI evaluation counts for D. | Pending claims survive restart; unknown payment outcomes keep stock held. Results distinguish invalid AI proposals from server-accepted deals. |
| A6 · H17–19 | A5 | Rerun domain checks against release configuration, pin model ID, provide seed/reset instructions and known behavior. | Domain signoff with commit and reproducible commands. | Clean DB can be seeded; rerunning seed does not overwrite an active reservation. |

## B · Member 2 with Codex — checkout, deployment and integration

| ID / window | Direct prerequisites | Subtasks | Deliverable | Pass gate |
|---|---|---|---|---|
| B1 · H0–2 | — | Test sandbox OAuth and buyer/business accounts, provision host/database, create payment migration and test quote adapter. | Health URL, environment template and checkout test harness. | Hosted health check works; server authenticates to Sandbox. Secrets stay server-side. |
| B2 · H2–6 | B1 | Build order creation, PayPal JS approval button and authorization endpoint with test-only USD 1 adapter. Persist operation and provider identifiers. | Standalone sandbox checkout, reusable CheckoutButton component. | Fresh browser authorizes USD 1 and shows the authorization ID. Cancellation creates no authorization. |
| B3 · H6–10 | B2 | Implement capture after simulated fulfillment, payment status, stable idempotency key per operation and reconciliation after lost responses. Build production asset/deployment scripts. | Tested payment module, hosted checkout harness and deployment configuration. | Real sandbox capture yields a capture ID. Injected lost response + retry resolves one logical operation. Pending state cannot start a second payment. |
| B4 · H10–14 | B3; **external A4, C3** | Mount A’s router and adapter, mount C’s production build and replace mock button with B’s component. Deploy, inspect migration order and complete both scenarios. | Single deployed URL, commit, negotiation/quote/order/authorization IDs and no-deal trace. | Real agent deal → reserved quote → buyer approval → authorization for matching total. Refresh preserves it. No-deal reaches zero payment calls. |
| B5 · H14–19 | B4 | Test real handoff under stale quote, duplicate approval and unknown provider outcome. Recover claims idempotently. Rehearse clean install and fulfillment capture. | Tagged release candidate, payment evidence and setup steps for D. | One sandbox capture on a fresh authorized transaction, zero duplicates, no cross-session access. Startup/refresh preserve persisted state. |
| B6 · H19–23 | B5 | Keep verified build available, reproduce any release-blocking defect and supply the last passing build or local run instructions. | Release URL and fallback instructions. | Fresh session reaches checkout; tagged build can be run with sandbox credentials. |

## C · Member 3 without Codex — complete buyer interface

| ID / window | Direct prerequisites | Subtasks | Deliverable | Pass gate |
|---|---|---|---|---|
| C1 · H0–2 | — | Scaffold React/Vite/TypeScript, build local fixture adapter and placeholder checkout component. | Runnable UI with scenario switch and the H0 public view. | Starts locally without database, model key or PayPal credentials. |
| C2 · H2–6 | C1 | Build requirement form and offer history. Show delivered-by date, quantities and total. Separate private budget entry from transcript. | Buyer request and negotiation screens. | User sees why the USD 330 offer misses Friday. Invalid inputs cannot start negotiation. |
| C3 · H6–10 | C2 | Implement fetch adapter, status restoration, disabled checkout and component slot for B. Build production assets. | Buildable frontend and integration instructions handed to B. | Fixture tests cover valid split, shortfall, expiry and retry. API mode uses documented paths. Production build succeeds without B’s code using the placeholder. |
| C4 · H10–17 | C3 | Test browser back, refresh, narrow viewport, expired and pending states, keyboard controls and double-clicks. Keep mock mode visibly labeled and production mode pointed to live endpoints. | UI regression checklist and fixes on C’s branch. | No active pay button for absent/expired quote; pending payment queries status; user can resume without replaying an order. |
| C5 · H17–19 | C4 | Provide final copy for errors and quote details, screenshot-free text guide to the screen sequence and UI build signoff. | UI release commit and rehearsal notes for D. | A teammate can follow the documented screen sequence using fixture mode; production build passes. |

## D · Member 4 without Codex — acceptance, recording and submission

| ID / window | Direct prerequisites | Subtasks | Deliverable | Pass gate |
|---|---|---|---|---|
| D1 · H0–3 | — | Label expected results for six cases: feasible split, impossible deadline, budget shortfall, forbidden color, competing buyers and ordinary order. Identify session, money and inventory evidence. | QA sheet with inputs, expected state, observed state and evidence columns. | Every case says whether a quote/payment is allowed and why. |
| D2 · H3–8 | D1 | Prepare manual steps for refresh, expiry, cancel, retry, unauthorized session and fulfillment. Map each defect to A, B or C. | Repeatable acceptance checklist and bug template. | A tester can recreate each scenario from the written initial state and see a binary pass/fail outcome. |
| D3 · H8–14 | D2 | Draft README, video storyboard, Devpost text and release link checklist. Time the script and prepare fresh buyer-session instructions. | Submission pack with marked placeholders for actual IDs, results and URLs. | Rehearsal fits under three minutes; claims of model calls, sandbox payment and simulated fulfillment are clearly distinguished. |
| D4 · H14–19 | D3; **external B4** | Test deployed build as a fresh buyer; run success/no-deal, cancel and refresh. Collect owner evidence for race/replay tests. Record first genuine end-to-end video as backup. | Acceptance log against commit plus backup recording. | Each observed mismatch has reproduction steps and owner. A passing recording shows a real quote and matching sandbox status. |
| D5 · H19–23 | D4; **external A6, B5, C5** | Retest changed paths on tagged commit. Finalize README, English video, open-source license, public repo, judge access and Devpost form. Submit as representative. | Accessible repo, runnable demo or test build, public YouTube video under three minutes and submission confirmation. | Open links signed out, verify exact release commit and save confirmation. H23–H24 remains available for upload recovery. |

## Integration gates and slip decisions

| Deadline | Passing evidence | Recovery owner and next move |
|---|---|---|
| H2 | A and B show real provider access independently. C has local UI. D has the first expected outcomes. | Provider owner diagnoses access while others continue from fixtures. |
| H10 | A4, B3 and C3 ready. B starts assembly. D continues rehearsal. | B can integrate A through the standalone checkout if C is late, or integrate C against the quote harness if A is late. Mark the partial milestone accurately. |
| H14 | B4 passes on one deployed commit. | B traces first broken interface; the module owner repairs it. Freeze optional features. If deployment alone fails, exercise the integrated build locally and preserve the recording. |
| H19 | D4 reports buyer-visible results. A6, B5, C5 attach owner evidence. | Prioritize mismatched amounts, false authorization, overselling, and cross-session access. Roll back broken changes and retest the passing candidate. |
| H23 | D5 passes and receipt is saved. | Use remaining buffer for broken links, upload or packaging. Disclose any unverified workflow in the submission. |

**Cross-member dependency audit.** B4 is the first meeting point for code. D4 needs the integrated URL. D5 needs release evidence from all three builders. These are the only tasks with external task prerequisites. Each builder owns fixes in their own module. Record the relevant commit and test output at every gate. A reviewer may inspect asynchronously.

**Cut order if hours slip.** Cut animations, sponsor integrations, second merchant and expanded evaluation first. Keep a real model decision, a merchant-backed quote, stock validation, buyer-approved sandbox authorization and an honest no-deal case. A saved recording is evidence of a real prior run; fixtures are explicitly labeled development aids.

## Working references

- [Official submission rules and judging criteria](https://paypalaihackathon.devpost.com/rules)
- [PayPal authorization and delayed capture](https://developer.paypal.com/checkout/delay-capture/)
- [PayPal idempotency guidance](https://developer.paypal.com/api/rest/reference/idempotency/)
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Deploy FastAPI on Render](https://render.com/docs/deploy-fastapi)

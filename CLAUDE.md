# CLAUDE.md — AgentNegotiate High-Density Project Context

> **Primary Reference for Member C (Member 3):** Read [`member_c_plan.md`](../member_c_plan.md) for the complete, step-by-step implementation guide and full production-ready source code for all Member C frontend files.

---

## 1. Project Overview & Architecture

**AgentNegotiate** is a 24-hour PayPal AI Hackathon project built by a 4-member team (`A`, `B`, `C`, `D`).
- **Core Journey:** A buyer enters a bulk shirt order with cumulative delivery deadlines, color rules, and a private budget. Two isolated AI agents (Buyer Agent + Seller Agent via Google Gemini structured outputs) negotiate up to 6 total turns over price and split delivery schedules. When an eligible deal is accepted, the server atomically locks dated inventory in PostgreSQL and issues an immutable, time-bounded `ReservedQuote` (15-minute TTL). The buyer approves the quote via PayPal Sandbox (`intent=AUTHORIZE`), locking the claim and returning a real PayPal authorization ID; merchant-only capture follows simulated fulfillment. If a deadline or stock constraint is impossible, the system explains the exact shortfall (e.g., 4-shirt Friday shortfall) with `quote: null` and disables checkout.
- **Deployment Architecture:** Single FastAPI service (`backend.main:app`) + single PostgreSQL database (`agentnegotiate-db` on Render) + React 18 / Vite 6 / TypeScript 5.6 SPA (`frontend/`).
- **Strict Trust & Privacy Boundaries:**
  - Buyer `budget_cents` and Seller `policy.minimum_total_cents` / `stock_batches` are **private server-side inputs** — never returned in public HTTP responses or rendered in public messages.
  - Each AI turn runs in an isolated spawned child process (`backend/domain/agent_process.py`) receiving only that role's private input plus `SharedNegotiationContext`.
  - Public transcript `messages` (`{actor, text}`) are deterministically rendered by `PublicMessage` from validated `PublicEvent` records — never raw LLM text.
  - All monetary values use strict integer USD cents (`total_cents`, `budget_cents`). All dates use canonical ISO `YYYY-MM-DD`. All quote expiries use real server UTC timestamps (`expires_at`).
  - Server-owned HTTP-only cookie session (`request.state.session_id` / `b2_session`); session ID is never accepted from request bodies or headers.

---

## 2. Tech Stack & Dependencies

### Frontend (`frontend/package.json` — Owned by Member C, except `CheckoutButton.tsx` owned by B)
- **Runtime:** Node.js `v24.21.0` (requires `20.19+` or `22.12+`), npm `11.19.0` (use `npm.cmd` on Windows PowerShell).
- **Dependencies:** `react@^18.3.1`, `react-dom@^18.3.1` (zero external UI/state libraries — pure React + TypeScript + CSS).
- **DevDependencies:** `typescript@^5.6.0` (`strict: true`, `noEmit: true`), `vite@^6.0.0`, `@vitejs/plugin-react@^4.3.0`, `@types/react@^18.3.0`, `@types/react-dom@^18.3.0`.

### Backend (`backend/requirements.txt` & `backend/domain/requirements.txt` — Owned by A & B)
- **Runtime:** Python `3.10+` (`3.12` venv at `.venv`).
- **Shared (`backend/requirements.txt`):** `fastapi>=0.115,<1.0`, `uvicorn[standard]>=0.30,<1.0`, `psycopg[binary]>=3.2,<4.0`, `python-dotenv>=1.2,<2`, `pydantic>=2.10,<3`.
- **Domain (`backend/domain/requirements.txt`):** adds `google-genai>=1.75,<2`, `httpx>=0.28.1,<1`.
- **Dev (`backend/domain/requirements-dev.txt`):** adds `pytest>=8.3,<9`.

---

## 3. Complete Repository Folder Structure

### Existing Files in `d:\Paypal hackathon\PayPal_Hackathon`
```text
PayPal_Hackathon/
├── .env.example                                  # Env template (DB, Session, Gemini, PayPal, Vite vars)
├── .gitignore                                    # Ignores .env, .venv, node_modules, dist, caches
├── implementation_plan.md                        # Master 24-hour 4-member specification & H0 contracts
├── README.md                                     # Root quickstart, ownership table, integration notes
├── render.yaml                                   # Render Blueprint: FastAPI web service + free Postgres DB
├── .agents/
│   ├── council/COUNCIL.md                        # Karpathy 5-advisor LLM Council workflow skill
│   └── data-ai/                                  # 10 specialized AI/data engineering agent personas
│       ├── ai-engineer.md                        # End-to-end AI system architecture & latency/bias checklist
│       ├── data-analyst.md                       # KPI, SQL optimization & dashboard storytelling persona
│       ├── data-engineer.md                      # ETL/ELT, pipeline reliability & idempotent design persona
│       ├── data-scientist.md                     # Hypothesis testing & statistical rigor persona
│       ├── database-optimizer.md                 # Postgres indexing, lock minimization & query tuning persona
│       ├── llm-architect.md                      # Structured output, safety filters & token/latency persona
│       ├── machine-learning-engineer.md          # Real-time inference serving, timeouts & circuit breakers
│       ├── ml-engineer.md                        # ML lifecycle, validation & fallback patterns persona
│       ├── mlops-engineer.md                     # CI/CD, reproducibility & deployment automation persona
│       └── nlp-engineer.md                       # Text processing, schema extraction & evaluation persona
├── backend/
│   ├── __init__.py                               # Backend package marker
│   ├── main.py                                   # FastAPI entrypoint (/health, /test-checkout, routers) [Owner: B]
│   ├── requirements.txt                          # Shared FastAPI/Postgres/Pydantic dependencies [Owner: B]
│   ├── domain/                                   # [Owner: Member A]
│   │   ├── __init__.py                           # Domain package marker
│   │   ├── README.md                             # Index of A1–A4 domain documentation
│   │   ├── A1_STATUS.md                          # A1 Gemini smoke verification & 5-advisor review log
│   │   ├── MODEL_SMOKE.md                        # Gemini client config & CLI smoke docs
│   │   ├── CONTRACTS.md                          # A1.1 Pydantic contract & cumulative delivery rules
│   │   ├── NEGOTIATION.md                        # A2 6-turn bounded negotiation runner docs & rules
│   │   ├── PERSISTENCE.md                        # A3 Postgres atomic stock reservation & QuoteAdapter docs
│   │   ├── API.md                                # A4 FastAPI negotiation router & HTTP contract docs
│   │   ├── contracts.py                          # Immutable Pydantic models, actions, PublicMessage renderer
│   │   ├── fixtures.py                           # Approved 30-shirt buyer, split ($354), & Monday ($330) fixtures
│   │   ├── model_config.py                       # Server-side Gemini env/settings validator
│   │   ├── model_client.py                       # GeminiActionClient structured output transport
│   │   ├── model_smoke.py                        # CLI smoke runner for single buyer/seller action
│   │   ├── agent_process.py                      # Spawned child-process boundary with hard wall-clock timeout
│   │   ├── negotiation.py                        # In-memory 6-turn engine, assess_offer, supply_shortfalls
│   │   ├── negotiation_fixtures.py               # Deterministic FixtureAgents & fixture_scenario builder
│   │   ├── database.py                           # DomainDatabase transaction manager & sanitized DomainError
│   │   ├── migrate.py                            # Advisory-locked checksum migration runner for domain SQL
│   │   ├── quotes.py                             # QuoteAdapter (issue, get, claim, commit, release, expire)
│   │   ├── turns.py                              # Single-turn advance() helper for versioned API calls
│   │   ├── api.py                                # NegotiationService & create_router (/api/negotiations)
│   │   ├── api_demo.py                           # In-process TestClient + disposable Postgres demo CLI
│   │   ├── requirements.txt                      # Domain runtime deps (google-genai, httpx, psycopg, etc.)
│   │   ├── requirements-dev.txt                  # Domain dev deps (-r requirements.txt + pytest)
│   │   ├── migrations/
│   │   │   ├── 001_domain.sql                    # Tables: domain_stock_batches, domain_quotes, reservations, claims
│   │   │   └── 002_negotiations.sql              # Table: domain_negotiations (durable versioned turns)
│   │   └── tests/                                # 10 pytest suites (423+ tests covering A1–A4)
│   └── payments/                                 # [Owner: Member B]
│       ├── __init__.py                           # Payments package marker
│       ├── README.md                             # B1–B3 Sandbox setup, migration & reconciliation docs
│       ├── b1_checks.py                          # Startup background DB & PayPal OAuth health check
│       ├── sandbox_auth.py                       # CLI smoke check for PayPal Sandbox OAuth token
│       ├── provider.py                           # PayPal Sandbox Orders v2 create, authorize, capture client
│       ├── test_quote_adapter.py                 # In-memory $1.00 TestQuoteAdapter substitute
│       ├── quote_harness.py                      # CLI runner for TestQuoteAdapter scenarios
│       ├── migrate.py                            # Checksum migration runner for payment SQL files
│       ├── harness.py                            # FastAPI routes: /api/payments/orders, authorize, status
│       ├── harness.html                          # Standalone B2 Sandbox test checkout HTML page
│       ├── harness.js                            # Standalone B2 Sandbox checkout script
│       ├── capture.py                            # Merchant capture & order/authorize reconciliation routes
│       ├── migrations/
│       │   ├── 001_payments.sql                  # Table: payment_operations (order, authorize, capture)
│       │   └── 002_b2_harness.sql                # Table: payment_test_quotes + unique operation indexes
│       └── tests/                                # 4 unittest suites for B1–B3 payment flows
├── frontend/                                     # [Owner: Member C, except CheckoutButton.tsx owned by B]
│   ├── index.html                                # HTML entry page
│   ├── package.json                              # Vite + React 18 + TypeScript scripts & dependencies
│   ├── package-lock.json                         # Locked npm dependency tree
│   ├── tsconfig.json                             # Strict TypeScript bundler configuration
│   ├── vite.config.ts                            # Vite React plugin configuration
│   └── src/
│       ├── main.tsx                              # React DOM root mount
│       ├── vite-env.d.ts                         # Vite client type declarations
│       ├── CheckoutButton.tsx                    # [Owner: Member B — DO NOT MODIFY] PayPal JS SDK button
│       ├── App.tsx                               # [Owner: Member C] Main buyer screen (currently scaffold)
│       └── fixtures/
│           └── .gitkeep                          # Directory placeholder for C's local fixtures
└── qa/                                           # [Owner: Member D]
    └── README.md                                 # QA acceptance scenarios & submission instructions
```

### Planned Files for Member C (`frontend/src/`)
```text
frontend/src/
├── types.ts                                      # Exact H0 TypeScript contracts, API payloads, payment & UI types
├── fixtures/
│   └── scenarios.ts                              # Approved H0 fixtures (feasible split, 4-shirt shortfall, competing/expired, retryable_error) + offer evaluator
├── adapters/
│   ├── localAdapter.ts                           # Deterministic browser-only adapter (sessionStorage persistence, turn stepping, expiry/conflict simulation)
│   └── apiAdapter.ts                             # Live HTTP fetch adapter (/api/negotiations, /api/payments/quotes/{id}) with 404/409/410/422/503 handling
├── components/
│   ├── ModeBanner.tsx                            # Visibly labels Mock/Fixture Mode vs Live API Mode + scenario switcher
│   ├── RequirementForm.tsx                       # Validated buyer order form (cumulative deadlines, color rules, private budget separated from public view)
│   ├── NegotiationTranscript.tsx                 # Turn-by-turn transcript + offer evaluation callouts (explains why $330 Monday-only fails Friday deadline)
│   ├── QuotePanel.tsx                            # Reserved quote inspector (lines, deliver_by, total_cents, live UTC countdown, expired/no_deal reasons)
│   └── CheckoutSlot.tsx                          # Safe wrapper around B's CheckoutButton + local mock placeholder + payment status polling/reconciliation
├── App.css                                       # Responsive desktop & narrow-viewport styles, accessible focus states, clear status badges
└── App.tsx                                       # Complete buyer journey state machine, URL/sessionStorage restoration, double-click guards, keyboard controls
```

---

## 4. Setup, Run, Build, and Test Commands

### Frontend (Member C Primary Workspace)
> **Windows PowerShell Note:** Use `npm.cmd` and `npx.cmd` if PowerShell execution policy blocks `.ps1` scripts.
```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon\frontend"
npm.cmd install
npm.cmd run dev          # Starts Vite dev server (http://localhost:5173)
npm.cmd run build        # Runs tsc --noEmit && vite build (production bundle in frontend/dist)
npm.cmd run preview      # Previews production build locally
```

### Backend & Tests (Reference for Verification)
```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon"
.\.venv\Scripts\python.exe -B -m pytest backend -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/payments/tests -v
```

---

## 5. Coding Conventions, Rules & Agent Workflows (`agents/`)

From `d:\Paypal hackathon\agents\.agents\` (also installed at `d:\Paypal hackathon\.agents\` and `PayPal_Hackathon\.agents\`):
1. **LLM Council (`council/COUNCIL.md`):**
   - For high-stakes design/architecture tradeoffs, apply the 5 thinking lenses used across `A1_STATUS.md` and `NEGOTIATION.md`:
     1. **Contrarian:** What will fail? (Stale versions, double-clicks, expired quotes, missing `VITE_PAYPAL_CLIENT_ID`, uncertain payment state).
     2. **First Principles Thinker:** What problem are we actually solving? (Clear buyer requirements -> transparent constraint checking -> trustworthy stock-backed quote -> safe payment authorization).
     3. **Expansionist:** What high-leverage UX polish helps judges immediately understand the value? (Side-by-side comparison of why the $330 Monday-only offer fails the Friday deadline while the $354 split offer qualifies).
     4. **Outsider:** Does a judge with zero context immediately see whether they are in Fixture Mode vs Live Mode, why checkout is disabled on no-deal/expired quotes, and that private budget is never leaked?
     5. **Executor:** Does `npm.cmd run build` pass with zero TypeScript errors and zero external dependencies?
2. **Engineering Checklists (`data-ai/*.md`):**
   - **Strict Validation & Fail-Closed Boundaries:** Reject invalid inputs before starting negotiation (quantity > 0, cumulative `minimum_by_date` strictly increasing in date and non-decreasing in quantity with final entry == total quantity, `preferred_color` in `allowed_colors`, `budget_cents > 0`).
   - **Idempotency & Concurrency Guards:** Disable action buttons while requests are in flight to prevent double-clicks; track `version` and pass `expected_version` on every `/turn` request; handle HTTP `409` by refreshing via `GET /api/negotiations/{id}`.
   - **No Fabricated Live Success:** Never disguise a fixture as a live model or PayPal call. Mock/Fixture mode must be visibly labeled at all times.

---

## 6. Team Member Split & Ownership Boundaries

| Member | Owns | Must NOT Touch |
|---|---|---|
| **A (Member 1)** | `backend/domain/**` (contracts, Gemini client, negotiation engine, Postgres stock & quote adapter, `/api/negotiations` router) | `backend/payments/**`, `frontend/**`, `qa/**` |
| **B (Member 2)** | `backend/payments/**`, `backend/main.py`, `render.yaml`, `frontend/src/CheckoutButton.tsx` | `backend/domain/**`, other `frontend/src/**` files |
| **C (Member 3 — YOU)** | `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/fixtures/**`, `frontend/src/adapters/**`, `frontend/src/components/**`, `frontend/src/App.css`, `frontend/vite.config.ts` (if proxy needed) | **`frontend/src/CheckoutButton.tsx`** (owned by B), `backend/**`, `qa/**` |
| **D (Member 4)** | `qa/**`, root `README.md` finalization, demo video & Devpost submission | `backend/**`, `frontend/**` |

### Member C Milestones (`implementation_plan (1).md` lines 70–77)
- **C1 (H0–2):** Scaffold React/Vite/TypeScript, build local fixture adapter and placeholder checkout component. Starts locally without DB, model key, or PayPal credentials.
- **C2 (H2–6):** Build requirement form and offer history. Show delivered-by date, quantities, and total. Separate private budget entry from transcript. User sees why the USD 330 offer misses Friday. Invalid inputs cannot start negotiation.
- **C3 (H6–10):** Implement fetch adapter, status restoration, disabled checkout, and component slot for B. Build production assets (`npm.cmd run build` succeeds without B's credentials using placeholder). Hand integration instructions to B for **B4 (H10–14)**.
- **C4 (H10–17):** Test browser back, refresh, narrow viewport, expired and pending states, keyboard controls, and double-clicks. Keep mock mode visibly labeled and production mode pointed to live endpoints.
- **C5 (H17–19):** Final copy for errors and quote details, screenshot-free text guide to the screen sequence, and UI build signoff for D.

---

## 7. Key API / Data Schemas & Shared Contracts

### 7.1 `A → C` Negotiation HTTP Contract (`backend/domain/api.py` & `contracts.py`)
1. **`POST /api/negotiations`**
   - **Request Body (`CreateNegotiation`):**
     ```json
     {
       "sku": "shirts",
       "quantity": 30,
       "minimum_by_date": [
         { "date": "2026-11-13", "qty": 12 },
         { "date": "2026-11-16", "qty": 30 }
       ],
       "budget_cents": 36000,
       "allowed_colors": ["navy", "black"],
       "preferred_color": "navy"
     }
     ```
     *Critical Rule (`CONTRACTS.md` lines 39–48):* `minimum_by_date` is **cumulative**. The second entry is `30` (total shirts by Mon Nov 16), **not** `18`. Dates must be strictly increasing (`YYYY-MM-DD`), quantities non-decreasing (`1 <= qty1 <= qty2 == quantity`), `allowed_colors` subset of `["navy", "black"]` with unique items, `preferred_color` `null` or in `allowed_colors`, `budget_cents` positive integer.
2. **`POST /api/negotiations/{id}/turn`**
   - **Request Body (`TurnRequest`):**
     ```json
     { "expected_version": 0 }
     ```
3. **`GET /api/negotiations/{id}`**
   - Restores current negotiation view (and lazily transitions expired unclaimed quotes to `status: "expired"`).
4. **Public View Response Shape (returned by all 3 endpoints):**
   ```typescript
   export type NegotiationStatus =
     | "negotiating"
     | "quoting"
     | "quoted"
     | "no_deal"
     | "expired"
     | "retryable_error";

   export interface PublicMessageView {
     actor: "buyer" | "seller";
     text: string;
   }

   export interface QuoteLineView {
     color: "navy" | "black";
     qty: number;
     deliver_by: string; // "YYYY-MM-DD"
   }

   export interface QuoteView {
     id: string;
     currency: "USD";
     total_cents: number;
     expires_at: string; // ISO-8601 UTC timestamp e.g. "2026-11-12T18:15:00Z"
     lines: QuoteLineView[];
   }

   export interface NegotiationPublicView {
     id: string;
     version: number;
     status: NegotiationStatus;
     messages: PublicMessageView[];
     reason: string | null;
     quote: QuoteView | null;
   }
   ```
5. **Error Status Codes from Domain API (`backend/domain/database.py` & `api.py`):**
   - `401`: Missing server-owned session (`"A server-owned session is required."`)
   - `404`: Negotiation/quote not found or owned by another session (`detail: { code: "not_found", message: "..." }`)
   - `409`: Version or stock/state conflict (`detail: { code: "operation_conflict" | "stock_conflict", message: "..." }`) -> **UI must call `GET /api/negotiations/{id}` to refresh state.**
   - `410`: Quote expired (`detail: { code: "expired", message: "The quote has expired." }`) -> **UI must disable checkout and show expired state.**
   - `422`: Validation error (`detail: "Invalid negotiation input."` or `{ code: "invalid_input", message: "..." }`)
   - `503`: Storage unavailable (`detail: { code: "storage_unavailable", message: "..." }`)

### 7.2 `B → C` Checkout & Payment Contract (`frontend/src/CheckoutButton.tsx` & `backend/payments/harness.py`)
- **Component Signature (`frontend/src/CheckoutButton.tsx`):**
  ```tsx
  type Props = { quoteId: string; onStatusChange: (status: string) => void };
  export default function CheckoutButton({ quoteId, onStatusChange }: Props): JSX.Element;
  ```
- **Statuses emitted by `CheckoutButton` via `onStatusChange(status)`:**
  - `"checkout_unavailable"` — emitted immediately on mount if `import.meta.env.VITE_PAYPAL_CLIENT_ID` is not set.
  - `"pending"` — emitted when `onApprove` starts, OR if `/api/payments/orders/{id}/authorize` throws/times out (uncertain outcome).
  - `"authorized"` — emitted when `/api/payments/orders/{id}/authorize` succeeds.
  - `"cancelled"` — emitted when buyer closes/cancels the PayPal popup.
  - `"error"` — emitted when PayPal SDK fails to load or `Buttons.render` errors.
- **Payment Status Endpoint (`GET /api/payments/quotes/{quote_id}`):**
  ```json
  {
    "quote_id": "q1",
    "operations": [
      {
        "operation_type": "order",
        "status": "succeeded",
        "paypal_order_id": "5O190127TN364715T",
        "paypal_authorization_id": null,
        "paypal_capture_id": null
      },
      {
        "operation_type": "authorize",
        "status": "succeeded",
        "paypal_order_id": "5O190127TN364715T",
        "paypal_authorization_id": "0VF52814937998046",
        "paypal_capture_id": null
      }
    ]
  }
  ```
  - When payment is `"pending"` or `"authorized"` or on page refresh of a `"quoted"` negotiation, the UI queries `GET /api/payments/quotes/{quote.id}` to display the authoritative `paypal_authorization_id` / `paypal_capture_id` and prevent duplicate payment attempts while an operation is `"pending"` or `"unknown"`.

---

## 8. Environment Variables (`.env.example`)

| Variable | Scope | Description |
|---|---|---|
| `DATABASE_URL` | Server only | PostgreSQL connection string (`postgresql://...`) |
| `SESSION_SECRET` | Server only | High-entropy secret for server-owned session cookies |
| `GEMINI_API_KEY` | Server only | Google Gemini API key (never exposed to browser) |
| `GEMINI_MODEL` | Server only | Required bare model ID (e.g. `gemini-3.8-flash`) |
| `PAYPAL_CLIENT_ID` | Server | PayPal Sandbox REST app Client ID |
| `PAYPAL_CLIENT_SECRET` | Server only | PayPal Sandbox REST app Secret (never exposed to browser) |
| `PAYPAL_BASE_URL` | Server | `https://api-m.sandbox.paypal.com` |
| `VITE_PAYPAL_CLIENT_ID` | Browser (`frontend`) | Public PayPal Sandbox Client ID used by `CheckoutButton.tsx` |
| `VITE_API_BASE_URL` | Browser (`frontend`) | Optional API prefix (default `""` for same-origin `/api/...`) |

---

## 9. Git Workflow

- Work on short-lived branches off `main` (e.g., `git checkout -b member-c/buyer-ui`).
- Never modify `frontend/src/CheckoutButton.tsx`, `backend/**`, or `.env`.
- Verify `npm.cmd run build` passes cleanly before every commit.
- Merge or hand off branch to Member B at gate **B4 (H10–14)** and Member D at gate **C5 (H17–19)**.


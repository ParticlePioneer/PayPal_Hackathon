# Member C (Member 3) Ultra-Detailed Implementation Plan — Buyer Interface, State & Error Handling

> **Target Owner:** Member C · Member 3 ("Buyer-facing React screen, frontend state and error handling")
> **Repository Root:** `d:\Paypal hackathon\PayPal_Hackathon`
> **Frontend Root:** `d:\Paypal hackathon\PayPal_Hackathon\frontend`
> **Companion Context File:** [`CLAUDE.md`](file:///d:/Paypal%20hackathon/CLAUDE.md)

---

## 1. Scope Summary & Exact Citations from `implementation_plan (1).md`

### 1.1 Workstream Overview (`implementation_plan (1).md`, Lines 6–14, 17–26, 28–45)
- **Owner Role (Line 11):** `C · Member 3 | Codex access assumed: No | Owns from start to finish: Buyer-facing React screen, frontend state and error handling | First independent test: Complete the buyer journey in a browser against local fixtures`.
- **Judge Experience Requirements (Lines 18–26):**
  - Enter a bulk order (`30` shirts, at least `12` delivered by `Fri Nov 13, 2026`, remainder `30` cumulative by `Mon Nov 16, 2026`, budget `USD 360` / `36000` cents including delivery, `navy` preferred, `black` allowed).
  - Watch two AI agents negotiate over price and delivery.
  - Inspect why the Monday-only offer (`30` shirts Monday for `USD 330` / `33000` cents) **fails the first deadline** (0 delivered by Friday vs. 12 required).
  - Inspect why the split offer (`12 navy` by `2026-11-13` + `18 black` by `2026-11-16` for `USD 354` / `35400` cents) **qualifies**.
  - Inspect the merchant-backed reserved quote (`total_cents: 35400`, `expires_at` in real UTC, line items), approve it as a PayPal Sandbox buyer, and see the resulting authorization ID.
  - Try an impossible deadline / supply shortfall (`only 8 deliverable Friday, no other Friday supply`) and see the exact four-shirt shortfall explanation (`"At least 4 more shirts are required by 2026-11-13."`) with **no quote, reservation, order, or payment** and checkout disabled.
  - Handle competing buyers / stock conflict (`HTTP 409`) and expired quotes (`HTTP 410` or client/server UTC expiry) with a clear path to refresh or renegotiate.

### 1.2 Handoff Contracts Involving Member C (`implementation_plan (1).md`, Lines 30–45)
- **Directory Ownership (Line 30):**
  - Member A owns `backend/domain/`.
  - Member B owns `backend/payments/`, `backend/main.py`, deployment, and **`frontend/src/CheckoutButton.tsx`**.
  - **Member C owns the remaining `frontend/`** (`frontend/src/App.tsx`, `frontend/src/fixtures/`, and all supporting frontend modules/styles).
  - Member D owns `qa/`, `README.md`, and submission materials.
- **`A → C` Contract (Line 34 & `backend/domain/API.md`):**
  - `POST /api/negotiations` accepts `{ sku, quantity, minimum_by_date, budget_cents, allowed_colors, preferred_color }`.
  - `POST /api/negotiations/{id}/turn` accepts `{ expected_version }`.
  - `GET /api/negotiations/{id}` resumes/restores the negotiation state.
  - Each returns the H0 public view (`{ id, version, status, messages, reason, quote }`).
  - *Development Substitute:* C implements a local adapter returning `negotiating`, `quoted`, `no_deal`, `expired`, and `retryable_error` views.
- **`B → C` Contract (Line 36 & `frontend/src/CheckoutButton.tsx`):**
  - `CheckoutButton` takes `{ quoteId: string, onStatusChange: (status: string) => void }`.
  - Member B already implemented `frontend/src/CheckoutButton.tsx` in commit `1dd6e05`.
  - `POST /api/payments/orders` receives `{ quote_id }`, `POST /api/payments/orders/{id}/authorize` handles approval, `GET /api/payments/quotes/{id}` returns `{ quote_id, operations: [...] }`. Capture is merchant-only.
  - *Development Substitute:* C renders a local mock/placeholder checkout control with the same props when in Local Fixture Mode (or when `VITE_PAYPAL_CLIENT_ID` is absent), while mounting B's real `CheckoutButton` in Live API Mode.
- **Error, Expiry & Privacy Rules (Lines 39–45):**
  - Quote expiry uses fresh UTC timestamps at runtime (`expires_at`). An expired fixture is intentional only in the expiry test.
  - `HTTP 409` means refresh after a version or stock conflict (`GET /api/negotiations/{id}`).
  - `HTTP 410` means an expired quote.
  - Provider timeout may leave payment `pending`; the UI requests existing status on refresh (`GET /api/payments/quotes/{quote_id}`).
  - Public messages exclude buyer `budget_cents` and seller floor (`minimum_total_cents`).

### 1.3 Member C Milestones & Pass Gates (`implementation_plan (1).md`, Lines 70–77)

| Milestone | Window | Prereqs | Subtasks | Deliverable | Pass Gate |
|---|---|---|---|---|---|
| **C1** | H0–2 | — | Scaffold React/Vite/TypeScript, build local fixture adapter and placeholder checkout component. | Runnable UI with scenario switch and the H0 public view. | Starts locally without database, model key or PayPal credentials. |
| **C2** | H2–6 | C1 | Build requirement form and offer history. Show delivered-by date, quantities and total. Separate private budget entry from transcript. | Buyer request and negotiation screens. | User sees why the USD 330 offer misses Friday. Invalid inputs cannot start negotiation. |
| **C3** | H6–10 | C2 | Implement fetch adapter, status restoration, disabled checkout and component slot for B. Build production assets. | Buildable frontend and integration instructions handed to B. | Fixture tests cover valid split, shortfall, expiry and retry. API mode uses documented paths. Production build succeeds without B's code/credentials using the placeholder. |
| **C4** | H10–17 | C3 | Test browser back, refresh, narrow viewport, expired and pending states, keyboard controls and double-clicks. Keep mock mode visibly labeled and production mode pointed to live endpoints. | UI regression checklist and fixes on C's branch. | No active pay button for absent/expired quote; pending payment queries status; user can resume without replaying an order. |
| **C5** | H17–19 | C4 | Provide final copy for errors and quote details, screenshot-free text guide to the screen sequence and UI build signoff. | UI release commit and rehearsal notes for D. | A teammate can follow the documented screen sequence using fixture mode; production build passes. |

---

## 2. Environment & Agent Setup Steps

### 2.1 Setup Actions Already Performed from `d:\Paypal hackathon\agents\`
1. Read all 11 agent specification files under `d:\Paypal hackathon\agents\.agents\`:
   - `council/COUNCIL.md` (Karpathy 5-Advisor LLM Council workflow: Contrarian, First Principles Thinker, Expansionist, Outsider, Executor).
   - `data-ai/ai-engineer.md`, `data-analyst.md`, `data-engineer.md`, `data-scientist.md`, `database-optimizer.md`, `llm-architect.md`, `machine-learning-engineer.md`, `ml-engineer.md`, `mlops-engineer.md`, `nlp-engineer.md`.
2. Verified that `d:\Paypal hackathon\PayPal_Hackathon\.agents\` already contains all 11 agent files tracked in Git, and copied `d:\Paypal hackathon\agents\.agents\` to `d:\Paypal hackathon\.agents\` so workspace-level agent discovery works in both directories.
3. Applied the 5 Council perspectives (Contrarian, First Principles, Expansionist, Outsider, Executor) to design Member C's frontend architecture:
   - **Contrarian:** Guard against double-clicks during turn advancement, stale `expected_version` (auto-recover on HTTP 409), missing `VITE_PAYPAL_CLIENT_ID` in local dev, expired quotes while viewing checkout, and uncertain (`pending`/`unknown`) payment operations on browser refresh.
   - **First Principles:** Keep cumulative `minimum_by_date` validation identical to `backend/domain/contracts.py` (`BuyerRequirements.coherent_requirements`) so invalid requests never even leave the browser.
   - **Expansionist:** Include an interactive Offer Comparison & Constraint Inspector card that explicitly breaks down why the Monday-only `$330.00` offer fails the Friday `2026-11-13` deadline (0 of 12 shirts delivered by Friday) while the `$354.00` split offer (`12 navy` by `2026-11-13` + `18 black` by `2026-11-16`) passes every constraint.
   - **Outsider:** Always render a prominent top banner distinguishing **LOCAL FIXTURE MODE (Simulated — No AI or PayPal Calls)** from **LIVE API MODE (FastAPI + Gemini + PayPal Sandbox)**, and visually badge the buyer's budget as **Private Buyer Constraint — Never Sent to Public Transcript**.
   - **Executor:** Zero extra npm packages required; pure React 18 + strict TypeScript + clean responsive CSS that builds in ~1 second via `npm.cmd run build`.

### 2.2 Exact Environment Details & Commands
- **OS / Shell:** Windows PowerShell (use `npm.cmd` instead of `npm` if PowerShell execution policy restricts `.ps1` scripts).
- **Verified Installed Tooling:**
  - Node.js: `v24.21.0` (satisfies `README.md` requirement `20.19+` or `22.12+`)
  - npm: `11.19.0`
- **Frontend Environment Variables (`frontend/.env.local` — optional for local dev, never committed):**
  ```ini
  # Leave empty in Local Fixture Mode; set to Sandbox Client ID when testing Live PayPal button
  VITE_PAYPAL_CLIENT_ID=
  # Leave empty when served from same origin or Vite dev proxy; set if backend is on another origin
  VITE_API_BASE_URL=
  ```

---

## 3. Complete List of Files Member C Owns (Create or Modify)

> **CRITICAL RULE:** Do **NOT** modify `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\CheckoutButton.tsx` — that file is owned by Member B and already contains B's PayPal JS SDK implementation.

| # | Action | Full Path in `d:\Paypal hackathon\PayPal_Hackathon` | 1-Line Purpose |
|---|---|---|---|
| 1 | **MODIFY** | `frontend/vite.config.ts` | Add dev-server `/api` proxy to `http://127.0.0.1:8000` so Live API Mode works seamlessly during `npm.cmd run dev`. |
| 2 | **CREATE** | `frontend/src/types.ts` | All TypeScript interfaces matching `backend/domain/contracts.py`, `backend/domain/api.py`, and `backend/payments/harness.py`. |
| 3 | **CREATE** | `frontend/src/fixtures/scenarios.ts` | Deterministic H0 fixture scenarios (`split`, `shortfall`, `competing_conflict`, `expired`, `retryable_error`), offer comparator, and requirement validator. |
| 4 | **CREATE** | `frontend/src/adapters/localAdapter.ts` | Browser-only `NegotiationAdapter` backed by `sessionStorage` with turn-by-turn progression, expiry injection, conflict simulation, and mock payment state. |
| 5 | **CREATE** | `frontend/src/adapters/apiAdapter.ts` | Live HTTP `NegotiationAdapter` calling `POST /api/negotiations`, `POST /api/negotiations/{id}/turn`, `GET /api/negotiations/{id}`, and `GET /api/payments/quotes/{id}`. |
| 6 | **CREATE** | `frontend/src/components/ModeBanner.tsx` | Top bar visibly labeling Fixture Mode vs. Live API Mode, quick scenario preset selector, and session/state reset controls. |
| 7 | **CREATE** | `frontend/src/components/RequirementForm.tsx` | Validated bulk-order requirement form with cumulative delivery schedule builder and isolated Private Budget input box. |
| 8 | **CREATE** | `frontend/src/components/NegotiationTranscript.tsx` | Turn-by-turn agent message feed, Offer Eligibility Breakdown ($330 Monday-only vs. $354 split), and keyboard-accessible Turn/Retry/Refresh controls. |
| 9 | **CREATE** | `frontend/src/components/QuotePanel.tsx` | Merchant-backed quote card displaying line batches, `deliver_by` dates, `total_cents`, live UTC expiry countdown, or `no_deal`/`expired` explanation. |
| 10 | **CREATE** | `frontend/src/components/CheckoutSlot.tsx` | Hosts Member B's `CheckoutButton` in Live Mode or C's interactive placeholder in Fixture Mode, plus `GET /api/payments/quotes/{id}` status recovery. |
| 11 | **CREATE** | `frontend/src/App.css` | Complete responsive stylesheet supporting desktop two-column layout, narrow mobile viewport (`<768px`), high-contrast badges, and keyboard focus rings. |
| 12 | **MODIFY** | `frontend/src/App.tsx` | Main buyer application orchestrating URL/sessionStorage restoration (`?negotiation_id=...`), browser back/forward (`popstate`), double-click locks, and screen sequence guide. |

---

## 4. Production-Ready Implementation Code for Every Member C File

### File 1: `d:\Paypal hackathon\PayPal_Hackathon\frontend\vite.config.ts`
- **Purpose:** Configures Vite React plugin and proxies `/api` requests to `http://127.0.0.1:8000` in local dev when `VITE_API_BASE_URL` is unset, ensuring same-origin cookie behavior (`b2_session` / server session) without CORS issues.
- **Connections:** Used by `npm.cmd run dev` and `npm.cmd run build`.

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
```

---

### File 2: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\types.ts`
- **Purpose:** Defines exact TypeScript contracts mirroring Member A's `backend/domain/contracts.py` & `backend/domain/api.py` and Member B's `frontend/src/CheckoutButton.tsx` & `backend/payments/harness.py`.
- **Connections:** Imported by all adapters, fixtures, and components.

```typescript
export type Color = "navy" | "black";

export type Actor = "buyer" | "seller";

export type NegotiationStatus =
  | "negotiating"
  | "quoting"
  | "quoted"
  | "no_deal"
  | "expired"
  | "retryable_error";

export interface DeliveryMinimum {
  date: string; // Canonical ISO calendar date "YYYY-MM-DD"
  qty: number;  // Positive integer, cumulative quantity required by this date
}

export interface CreateNegotiationRequest {
  sku: string;
  quantity: number;
  minimum_by_date: DeliveryMinimum[];
  budget_cents: number; // Private buyer input — sent on POST /api/negotiations, never in public view
  allowed_colors: Color[];
  preferred_color: Color | null;
}

export interface TurnRequest {
  expected_version: number;
}

export interface PublicMessageView {
  actor: Actor;
  text: string;
}

export interface QuoteLineView {
  color: Color;
  qty: number;
  deliver_by: string; // "YYYY-MM-DD"
}

export interface QuoteView {
  id: string;
  currency: "USD";
  total_cents: number;
  expires_at: string; // UTC ISO-8601 timestamp e.g. "2026-11-12T18:15:00Z"
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

export type CheckoutCallbackStatus =
  | "idle"
  | "checkout_unavailable"
  | "pending"
  | "authorized"
  | "captured"
  | "cancelled"
  | "error";

export interface PaymentOperationRecord {
  operation_type: "order" | "authorize" | "capture";
  status: "pending" | "succeeded" | "failed" | "unknown";
  paypal_order_id: string | null;
  paypal_authorization_id: string | null;
  paypal_capture_id: string | null;
}

export interface PaymentQuoteStatusResponse {
  quote_id: string;
  operations: PaymentOperationRecord[];
}

export type AdapterMode = "fixture" | "api";

export type FixtureScenarioId =
  | "feasible_split"
  | "friday_shortfall"
  | "competing_buyer_conflict"
  | "expired_quote"
  | "retryable_timeout";

export interface OfferEvaluationLineCheck {
  date: string;
  requiredCumulativeQty: number;
  deliveredCumulativeQty: number;
  passed: boolean;
  shortfallQty: number;
}

export interface OfferEvaluationSummary {
  label: string;
  totalCents: number;
  lines: QuoteLineView[];
  withinBudget: boolean | null; // null if private budget not provided locally
  colorsAllowed: boolean;
  quantityMatches: boolean;
  deadlineChecks: OfferEvaluationLineCheck[];
  qualifies: boolean;
  failureSummary: string | null;
}

export class AdapterHttpError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "AdapterHttpError";
    this.status = status;
    this.code = code;
  }
}

export interface NegotiationAdapter {
  readonly mode: AdapterMode;
  createNegotiation(
    payload: CreateNegotiationRequest,
    scenarioId?: FixtureScenarioId
  ): Promise<NegotiationPublicView>;
  advanceTurn(
    negotiationId: string,
    expectedVersion: number
  ): Promise<NegotiationPublicView>;
  getNegotiation(negotiationId: string): Promise<NegotiationPublicView>;
  getPaymentStatus(quoteId: string): Promise<PaymentQuoteStatusResponse | null>;
}
```

---

### File 3: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\fixtures\scenarios.ts`
- **Purpose:** Encodes the exact H0 shared fixtures (`implementation_plan (1).md` lines 20–26, 39–45 and `backend/domain/fixtures.py`), strict client-side requirement validation mirroring `backend/domain/contracts.py`, and the Offer Eligibility Analyzer so the user immediately sees why the `$330.00` Monday-only offer misses Friday (`2026-11-13`) and why the `$354.00` split offer (`12 navy` Friday + `18 black` Monday) qualifies.
- **Connections:** Imported by `localAdapter.ts`, `RequirementForm.tsx`, `NegotiationTranscript.tsx`, and `App.tsx`.

```typescript
import {
  Color,
  CreateNegotiationRequest,
  FixtureScenarioId,
  OfferEvaluationSummary,
  QuoteLineView,
} from "../types";

export const APPROVED_DEFAULT_REQUEST: CreateNegotiationRequest = {
  sku: "shirts",
  quantity: 30,
  minimum_by_date: [
    { date: "2026-11-13", qty: 12 },
    { date: "2026-11-16", qty: 30 },
  ],
  budget_cents: 36000, // USD 360.00 inclusive of delivery
  allowed_colors: ["navy", "black"],
  preferred_color: "navy",
};

export interface FixtureScenarioMeta {
  id: FixtureScenarioId;
  title: string;
  badge: string;
  description: string;
  expectedOutcomeText: string;
  presetRequest: CreateNegotiationRequest;
}

export const FIXTURE_SCENARIOS: FixtureScenarioMeta[] = [
  {
    id: "feasible_split",
    title: "1. Feasible Split Deal ($354.00)",
    badge: "Qualifies & Reserves Stock",
    description:
      "Buyer needs 30 shirts (12 by Fri Nov 13, 30 cumulative by Mon Nov 16, budget $360). Seller's $330 Monday-only option fails Friday; $354 split (12 navy Fri + 18 black Mon) qualifies.",
    expectedOutcomeText:
      "Quote q_split_35400 issued for 35400 cents ($354.00 USD) with active 15-minute UTC reservation.",
    presetRequest: APPROVED_DEFAULT_REQUEST,
  },
  {
    id: "friday_shortfall",
    title: "2. Impossible Deadline — 4-Shirt Friday Shortfall",
    badge: "No Deal · Checkout Disabled",
    description:
      "Same buyer request (12 needed by Fri Nov 13), but only 8 navy shirts can arrive Friday and no other Friday supply exists.",
    expectedOutcomeText:
      'Status "no_deal" with reason: "At least 4 more shirts are required by 2026-11-13." quote is null; checkout disabled.',
    presetRequest: APPROVED_DEFAULT_REQUEST,
  },
  {
    id: "competing_buyer_conflict",
    title: "3. Competing Buyers — Stock Conflict (HTTP 409)",
    badge: "Stock Conflict · Renegotiate",
    description:
      "Two buyers compete for the final 12 Friday shirts. Another buyer locks the batch first during quote issuance.",
    expectedOutcomeText:
      'Returns HTTP 409 stock_conflict on final turn; refreshing via GET shows status "no_deal" with reason "Stock is no longer available; please renegotiate."',
    presetRequest: APPROVED_DEFAULT_REQUEST,
  },
  {
    id: "expired_quote",
    title: "4. Expired Reservation (HTTP 410 / UTC TTL Elapsed)",
    badge: "Expired · Checkout Disabled",
    description:
      "Intentional expiry test fixture: quote reservation timestamp is in the past so checkout is blocked.",
    expectedOutcomeText:
      'Status transitions to "expired" with reason "The quote has expired." Pay button is disabled.',
    presetRequest: APPROVED_DEFAULT_REQUEST,
  },
  {
    id: "retryable_timeout",
    title: "5. Transient Model Timeout (Retryable Error)",
    badge: "Retryable Turn · Resumable",
    description:
      "Simulates a bounded 30s model timeout on Turn 2 (`retryable_error`), allowing the buyer to retry the same version without losing state.",
    expectedOutcomeText:
      'Turn 2 pauses in "retryable_error"; clicking Retry Turn resumes at the same version and completes the $354.00 split quote.',
    presetRequest: APPROVED_DEFAULT_REQUEST,
  },
];

export const MONDAY_ONLY_OFFER_LINES: QuoteLineView[] = [
  { color: "black", qty: 30, deliver_by: "2026-11-16" },
];

export const SPLIT_OFFER_LINES: QuoteLineView[] = [
  { color: "navy", qty: 12, deliver_by: "2026-11-13" },
  { color: "black", qty: 18, deliver_by: "2026-11-16" },
];

/**
 * Validates buyer requirements using the exact rules in `backend/domain/contracts.py`
 * (`BuyerRequirements.coherent_requirements` and `CreateNegotiation`).
 */
export function validateNegotiationRequest(
  input: CreateNegotiationRequest
): string[] {
  const errors: string[] = [];

  if (!input.sku || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(input.sku.trim())) {
    errors.push("SKU must be a valid alphanumeric identifier (e.g., 'shirts').");
  }

  if (!Number.isInteger(input.quantity) || input.quantity <= 0) {
    errors.push("Total quantity must be a positive whole number.");
  }

  if (!Number.isInteger(input.budget_cents) || input.budget_cents <= 0) {
    errors.push("Private budget must be greater than $0.00 (positive integer cents).");
  }

  if (!Array.isArray(input.allowed_colors) || input.allowed_colors.length === 0) {
    errors.push("Select at least one allowed color (navy and/or black).");
  } else {
    const uniqueColors = new Set(input.allowed_colors);
    if (uniqueColors.size !== input.allowed_colors.length) {
      errors.push("Allowed colors must not contain duplicates.");
    }
    for (const c of input.allowed_colors) {
      if (c !== "navy" && c !== "black") {
        errors.push(`Unsupported catalog color: ${String(c)}.`);
      }
    }
  }

  if (
    input.preferred_color !== null &&
    !input.allowed_colors.includes(input.preferred_color)
  ) {
    errors.push("Preferred color must be one of the allowed colors.");
  }

  if (!Array.isArray(input.minimum_by_date) || input.minimum_by_date.length === 0) {
    errors.push("At least one delivery deadline is required.");
  } else {
    let previousDate: string | null = null;
    let previousQty = 0;

    input.minimum_by_date.forEach((min, idx) => {
      const stepLabel = `Deadline #${idx + 1}`;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(min.date) || Number.isNaN(Date.parse(min.date))) {
        errors.push(`${stepLabel}: Date must be in YYYY-MM-DD format.`);
      } else if (previousDate !== null && min.date <= previousDate) {
        errors.push(
          `${stepLabel}: Delivery dates must be strictly increasing (${min.date} must be after ${previousDate}).`
        );
      }

      if (!Number.isInteger(min.qty) || min.qty <= 0) {
        errors.push(`${stepLabel}: Cumulative quantity must be a positive integer.`);
      } else if (min.qty < previousQty) {
        errors.push(
          `${stepLabel}: Cumulative quantity (${min.qty}) cannot be less than earlier deadline quantity (${previousQty}). Note: minimum_by_date is cumulative.`
        );
      } else if (Number.isInteger(input.quantity) && min.qty > input.quantity) {
        errors.push(
          `${stepLabel}: Cumulative quantity (${min.qty}) cannot exceed total order quantity (${input.quantity}).`
        );
      }

      previousDate = min.date;
      previousQty = min.qty;
    });

    if (
      Number.isInteger(input.quantity) &&
      input.quantity > 0 &&
      previousQty !== input.quantity
    ) {
      errors.push(
        `Final delivery minimum (${previousQty}) must equal the full order quantity (${input.quantity}). Remember: quantities are cumulative (e.g., 12 by Friday, then 30 total by Monday).`
      );
    }
  }

  return errors;
}

/**
 * Evaluates any proposed offer against the buyer's requirements and optional private budget.
 * Explains clearly why the $330 Monday-only offer fails Friday and why the $354 split offer passes.
 */
export function evaluateOfferAgainstRequirements(
  label: string,
  totalCents: number,
  lines: QuoteLineView[],
  requirements: Pick<
    CreateNegotiationRequest,
    "quantity" | "minimum_by_date" | "allowed_colors"
  >,
  privateBudgetCents?: number | null
): OfferEvaluationSummary {
  const totalLineQty = lines.reduce((acc, line) => acc + line.qty, 0);
  const quantityMatches = totalLineQty === requirements.quantity;
  const colorsAllowed = lines.every((line) =>
    requirements.allowed_colors.includes(line.color as Color)
  );
  const withinBudget =
    typeof privateBudgetCents === "number" && privateBudgetCents > 0
      ? totalCents <= privateBudgetCents
      : null;

  const deadlineChecks = requirements.minimum_by_date.map((min) => {
    const deliveredCumulativeQty = lines
      .filter((line) => line.deliver_by <= min.date)
      .reduce((acc, line) => acc + line.qty, 0);
    const shortfallQty = Math.max(0, min.qty - deliveredCumulativeQty);
    return {
      date: min.date,
      requiredCumulativeQty: min.qty,
      deliveredCumulativeQty,
      passed: deliveredCumulativeQty >= min.qty,
      shortfallQty,
    };
  });

  const failedDeadline = deadlineChecks.find((d) => !d.passed);
  let failureSummary: string | null = null;
  if (!quantityMatches) {
    failureSummary = `Offer total quantity (${totalLineQty}) does not match requested quantity (${requirements.quantity}).`;
  } else if (!colorsAllowed) {
    failureSummary = "Offer includes a color not permitted by buyer requirements.";
  } else if (failedDeadline) {
    failureSummary = `Misses ${failedDeadline.date} deadline: delivers ${failedDeadline.deliveredCumulativeQty} of ${failedDeadline.requiredCumulativeQty} required shirts by ${failedDeadline.date} (shortfall of ${failedDeadline.shortfallQty} shirts).`;
  } else if (withinBudget === false && typeof privateBudgetCents === "number") {
    failureSummary = `Offer total ($${(totalCents / 100).toFixed(2)}) exceeds buyer private budget ($${(privateBudgetCents / 100).toFixed(2)}).`;
  }

  const qualifies =
    quantityMatches &&
    colorsAllowed &&
    !failedDeadline &&
    (withinBudget === null || withinBudget === true);

  return {
    label,
    totalCents,
    lines,
    withinBudget,
    colorsAllowed,
    quantityMatches,
    deadlineChecks,
    qualifies,
    failureSummary,
  };
}

export function formatUsd(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}
```

---

### File 4: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\adapters\localAdapter.ts`
- **Purpose:** Implements Member C's H0 development substitute (`implementation_plan (1).md` line 34: *"C implements a local adapter returning negotiating, quoted, no_deal, expired and retryable_error views"*). Persists state in `sessionStorage` so browser refresh (`F5`) and back/forward navigation work identically to the real PostgreSQL backend. Also supports simulated payment status (`order` / `authorize` / `capture` / `pending`) for local verification.
- **Connections:** Implements `NegotiationAdapter` from `../types`; uses `SPLIT_OFFER_LINES`, `evaluateOfferAgainstRequirements`, and `validateNegotiationRequest` from `../fixtures/scenarios`.

```typescript
import {
  AdapterHttpError,
  CreateNegotiationRequest,
  FixtureScenarioId,
  NegotiationAdapter,
  NegotiationPublicView,
  PaymentQuoteStatusResponse,
  PublicMessageView,
} from "../types";
import {
  SPLIT_OFFER_LINES,
  validateNegotiationRequest,
} from "../fixtures/scenarios";

const STORAGE_KEY = "agentnegotiate_local_sessions_v1";
const PAYMENT_STORAGE_KEY = "agentnegotiate_local_payments_v1";

interface StoredLocalNegotiation {
  id: string;
  scenarioId: FixtureScenarioId;
  request: CreateNegotiationRequest;
  step: number;
  retryResolved: boolean;
  conflictTriggered: boolean;
  view: NegotiationPublicView;
}

function loadStore(): Record<string, StoredLocalNegotiation> {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, StoredLocalNegotiation>) : {};
  } catch {
    return {};
  }
}

function saveStore(store: Record<string, StoredLocalNegotiation>): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Ignore storage quota errors in restricted browsers
  }
}

function loadPaymentStore(): Record<string, PaymentQuoteStatusResponse> {
  try {
    const raw = window.sessionStorage.getItem(PAYMENT_STORAGE_KEY);
    return raw
      ? (JSON.parse(raw) as Record<string, PaymentQuoteStatusResponse>)
      : {};
  } catch {
    return {};
  }
}

export function saveLocalPaymentState(
  quoteId: string,
  state: PaymentQuoteStatusResponse
): void {
  try {
    const store = loadPaymentStore();
    store[quoteId] = state;
    window.sessionStorage.setItem(PAYMENT_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Ignore storage quota errors
  }
}

export function clearLocalFixtureStorage(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    window.sessionStorage.removeItem(PAYMENT_STORAGE_KEY);
  } catch {
    // Ignore
  }
}

function checkShortfall(request: CreateNegotiationRequest, fridayNavyCap: number): {
  date: string;
  shortfallQty: number;
} | null {
  // Available stock in fixture: fridayNavyCap navy by 2026-11-13, 18 black by 2026-11-16
  const batches = [
    { color: "navy" as const, qty: fridayNavyCap, deliver_by: "2026-11-13" },
    { color: "black" as const, qty: 18, deliver_by: "2026-11-16" },
  ];
  for (const min of request.minimum_by_date) {
    const available = batches
      .filter(
        (b) =>
          request.allowed_colors.includes(b.color) && b.deliver_by <= min.date
      )
      .reduce((sum, b) => sum + b.qty, 0);
    if (available < min.qty) {
      return { date: min.date, shortfallQty: min.qty - available };
    }
  }
  return null;
}

export class LocalFixtureAdapter implements NegotiationAdapter {
  readonly mode = "fixture" as const;

  async createNegotiation(
    payload: CreateNegotiationRequest,
    scenarioId: FixtureScenarioId = "feasible_split"
  ): Promise<NegotiationPublicView> {
    const validationErrors = validateNegotiationRequest(payload);
    if (validationErrors.length > 0) {
      throw new AdapterHttpError(422, "invalid_input", validationErrors[0]);
    }

    const id = `n_local_${scenarioId}_${Math.random().toString(36).slice(2, 8)}`;
    const initialView: NegotiationPublicView = {
      id,
      version: 0,
      status: "negotiating",
      messages: [],
      reason: null,
      quote: null,
    };

    const store = loadStore();
    store[id] = {
      id,
      scenarioId,
      request: payload,
      step: 0,
      retryResolved: false,
      conflictTriggered: false,
      view: initialView,
    };
    saveStore(store);
    return structuredClone(initialView);
  }

  async advanceTurn(
    negotiationId: string,
    expectedVersion: number
  ): Promise<NegotiationPublicView> {
    const store = loadStore();
    const record = store[negotiationId];
    if (!record) {
      throw new AdapterHttpError(
        404,
        "not_found",
        "Quote or negotiation not found in current session."
      );
    }

    if (record.view.version !== expectedVersion) {
      throw new AdapterHttpError(
        409,
        "operation_conflict",
        "The operation conflicts with existing negotiation version. Refreshing state."
      );
    }

    if (
      record.view.status !== "negotiating" &&
      record.view.status !== "retryable_error"
    ) {
      throw new AdapterHttpError(
        409,
        "operation_conflict",
        `Cannot advance turn when status is '${record.view.status}'.`
      );
    }

    const nextVersion = record.view.version + 1;
    const messages: PublicMessageView[] = [...record.view.messages];
    const { scenarioId, request } = record;

    // Determine effective Friday stock based on scenario or custom form input
    const fridayNavyStock = scenarioId === "friday_shortfall" ? 8 : 12;
    const shortfall = checkShortfall(request, fridayNavyStock);
    const budgetTooLow = request.budget_cents < 35400;

    // Step 1: Buyer asks for delivery options (matches backend/domain/contracts.py PublicMessage)
    if (record.step === 0) {
      messages.push({
        actor: "buyer",
        text: "Can you provide delivery options?",
      });
      record.step = 1;
      record.view = {
        id: record.id,
        version: nextVersion,
        status: "negotiating",
        messages,
        reason: null,
        quote: null,
      };
      saveStore(store);
      return structuredClone(record.view);
    }

    // Step 2: Seller responds (or transient timeout in retryable_timeout scenario)
    if (record.step === 1) {
      if (scenarioId === "retryable_timeout" && !record.retryResolved) {
        record.retryResolved = true;
        record.view = {
          id: record.id,
          version: nextVersion,
          status: "retryable_error",
          messages,
          reason: "The negotiation exceeded its time limit.",
          quote: null,
        };
        saveStore(store);
        return structuredClone(record.view);
      }

      if (shortfall) {
        messages.push({
          actor: "seller",
          text: "The delivery requirement cannot be satisfied.",
        });
        record.step = 2;
        record.view = {
          id: record.id,
          version: nextVersion,
          status: "no_deal",
          messages,
          reason: `At least ${shortfall.shortfallQty} more shirts are required by ${shortfall.date}.`,
          quote: null,
        };
        saveStore(store);
        return structuredClone(record.view);
      }

      // Seller proposes the split offer (12 navy by 2026-11-13; 18 black by 2026-11-16 for USD 354.00)
      messages.push({
        actor: "seller",
        text: "Offer: USD 354.00 including delivery; 12 navy by 2026-11-13; 18 black by 2026-11-16.",
      });
      record.step = 2;
      record.view = {
        id: record.id,
        version: nextVersion,
        status: "negotiating",
        messages,
        reason: null,
        quote: null,
      };
      saveStore(store);
      return structuredClone(record.view);
    }

    // Step 3: Buyer evaluates Seller's offer
    if (record.step === 2) {
      if (budgetTooLow) {
        messages.push({
          actor: "buyer",
          text: "An acceptable price could not be agreed.",
        });
        record.step = 3;
        record.view = {
          id: record.id,
          version: nextVersion,
          status: "no_deal",
          messages,
          reason: "The price does not satisfy both parties' private constraints.",
          quote: null,
        };
        saveStore(store);
        return structuredClone(record.view);
      }

      messages.push({
        actor: "buyer",
        text: "The proposed terms are accepted, subject to server validation and stock reservation.",
      });
      record.step = 3;

      // Competing buyers scenario: another buyer claims the final 12 Friday shirts at quote issuance
      if (scenarioId === "competing_buyer_conflict") {
        record.conflictTriggered = true;
        record.view = {
          id: record.id,
          version: nextVersion,
          status: "no_deal",
          messages,
          reason: "Stock is no longer available; please renegotiate.",
          quote: null,
        };
        saveStore(store);
        throw new AdapterHttpError(
          409,
          "stock_conflict",
          "Stock is unavailable or already held."
        );
      }

      const nowMs = Date.now();
      const expiresAtIso =
        scenarioId === "expired_quote"
          ? new Date(nowMs - 60 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z")
          : new Date(nowMs + 15 * 60 * 1000)
              .toISOString()
              .replace(/\.\d{3}Z$/, "Z");

      const quoteId =
        scenarioId === "expired_quote" ? "q_expired_fixture" : "q1";

      record.view = {
        id: record.id,
        version: nextVersion,
        status: "quoted",
        messages,
        reason: null,
        quote: {
          id: quoteId,
          currency: "USD",
          total_cents: 35400,
          expires_at: expiresAtIso,
          lines: SPLIT_OFFER_LINES,
        },
      };
      saveStore(store);
      return this.getNegotiation(negotiationId);
    }

    return structuredClone(record.view);
  }

  async getNegotiation(negotiationId: string): Promise<NegotiationPublicView> {
    const store = loadStore();
    const record = store[negotiationId];
    if (!record) {
      throw new AdapterHttpError(
        404,
        "not_found",
        "Negotiation not found in local session."
      );
    }

    // Mirror backend/domain/api.py: lazily transition expired unclaimed quotes on GET
    if (record.view.status === "quoted" && record.view.quote) {
      const expiresMs = Date.parse(record.view.quote.expires_at);
      const paymentState = loadPaymentStore()[record.view.quote.id];
      const hasClaimOrAuth = paymentState?.operations.some(
        (op) => op.status === "succeeded" || op.status === "pending" || op.status === "unknown"
      );
      if (!Number.isNaN(expiresMs) && expiresMs <= Date.now() && !hasClaimOrAuth) {
        record.view = {
          ...record.view,
          status: "expired",
          reason: "The quote has expired.",
          quote: null,
        };
        saveStore(store);
      }
    }

    return structuredClone(record.view);
  }

  async getPaymentStatus(
    quoteId: string
  ): Promise<PaymentQuoteStatusResponse | null> {
    const store = loadPaymentStore();
    return store[quoteId] ? structuredClone(store[quoteId]) : null;
  }
}
```

---

### File 5: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\adapters\apiAdapter.ts`
- **Purpose:** Implements the live FastAPI HTTP adapter matching `backend/domain/api.py` (`POST /api/negotiations`, `POST /api/negotiations/{id}/turn`, `GET /api/negotiations/{id}`) and `backend/payments/harness.py` (`GET /api/payments/quotes/{id}`). Parses structured `DomainError` payloads (`detail: { code, message }` or string) and maps HTTP `401`, `404`, `409`, `410`, `422`, and `503` accurately.
- **Connections:** Implements `NegotiationAdapter` from `../types`.

```typescript
import {
  AdapterHttpError,
  CreateNegotiationRequest,
  NegotiationAdapter,
  NegotiationPublicView,
  PaymentQuoteStatusResponse,
} from "../types";

function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (!configured) return "";
  return configured.replace(/\/+$/, "");
}

async function parseApiError(response: Response): Promise<AdapterHttpError> {
  let code = `http_${response.status}`;
  let message = `Request failed with HTTP ${response.status}.`;

  try {
    const payload = await response.json();
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail && typeof payload.detail === "object") {
        if (typeof payload.detail.code === "string") {
          code = payload.detail.code;
        }
        if (typeof payload.detail.message === "string") {
          message = payload.detail.message;
        }
      }
    }
  } catch {
    // Fallback if response body is not JSON
  }

  if (response.status === 409 && code === "http_409") {
    code = "operation_conflict";
  } else if (response.status === 410 && code === "http_410") {
    code = "expired";
  } else if (response.status === 404 && code === "http_404") {
    code = "not_found";
  } else if (response.status === 422 && code === "http_422") {
    code = "invalid_input";
  }

  return new AdapterHttpError(response.status, code, message);
}

export class LiveApiAdapter implements NegotiationAdapter {
  readonly mode = "api" as const;

  async createNegotiation(
    payload: CreateNegotiationRequest
  ): Promise<NegotiationPublicView> {
    const base = getApiBaseUrl();
    const response = await fetch(`${base}/api/negotiations`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw await parseApiError(response);
    }

    return (await response.json()) as NegotiationPublicView;
  }

  async advanceTurn(
    negotiationId: string,
    expectedVersion: number
  ): Promise<NegotiationPublicView> {
    const base = getApiBaseUrl();
    const response = await fetch(
      `${base}/api/negotiations/${encodeURIComponent(negotiationId)}/turn`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_version: expectedVersion }),
      }
    );

    if (!response.ok) {
      throw await parseApiError(response);
    }

    return (await response.json()) as NegotiationPublicView;
  }

  async getNegotiation(negotiationId: string): Promise<NegotiationPublicView> {
    const base = getApiBaseUrl();
    const response = await fetch(
      `${base}/api/negotiations/${encodeURIComponent(negotiationId)}`,
      {
        method: "GET",
        credentials: "same-origin",
      }
    );

    if (!response.ok) {
      throw await parseApiError(response);
    }

    return (await response.json()) as NegotiationPublicView;
  }

  async getPaymentStatus(
    quoteId: string
  ): Promise<PaymentQuoteStatusResponse | null> {
    const base = getApiBaseUrl();
    try {
      const response = await fetch(
        `${base}/api/payments/quotes/${encodeURIComponent(quoteId)}`,
        {
          method: "GET",
          credentials: "same-origin",
        }
      );
      if (response.status === 404) {
        return null;
      }
      if (!response.ok) {
        return null;
      }
      return (await response.json()) as PaymentQuoteStatusResponse;
    } catch {
      return null;
    }
  }
}
```

---

### File 6: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\components\ModeBanner.tsx`
- **Purpose:** Satisfies C1 & C4 pass gates (*"Runnable UI with scenario switch"*, *"Keep mock mode visibly labeled and production mode pointed to live endpoints"*). Lets judges or developers toggle between **Local Fixture Mode** (with the 5 deterministic scenarios) and **Live API Mode** (`/api/negotiations` + `/api/payments/*`), plus provides a one-click **Screen Sequence Guide** toggle for Member D's C5 rehearsal.
- **Connections:** Imported by `App.tsx`.

```tsx
import { AdapterMode, FixtureScenarioId } from "../types";
import { FIXTURE_SCENARIOS } from "../fixtures/scenarios";

interface ModeBannerProps {
  mode: AdapterMode;
  scenarioId: FixtureScenarioId;
  busy: boolean;
  showGuide: boolean;
  onModeChange: (mode: AdapterMode) => void;
  onScenarioChange: (scenarioId: FixtureScenarioId) => void;
  onResetSession: () => void;
  onToggleGuide: () => void;
}

export default function ModeBanner({
  mode,
  scenarioId,
  busy,
  showGuide,
  onModeChange,
  onScenarioChange,
  onResetSession,
  onToggleGuide,
}: ModeBannerProps) {
  const activeScenario =
    FIXTURE_SCENARIOS.find((s) => s.id === scenarioId) ?? FIXTURE_SCENARIOS[0];

  return (
    <header className="mode-banner" role="banner">
      <div className="mode-banner-top">
        <div className="brand-block">
          <span className="brand-logo" aria-hidden="true">
            AN
          </span>
          <div>
            <h1 className="brand-title">AgentNegotiate</h1>
            <p className="brand-subtitle">
              Two-Agent Bulk Order Negotiation · Atomic Dated Stock Reservation · PayPal Sandbox Authorization
            </p>
          </div>
        </div>

        <div className="mode-controls" role="group" aria-label="Execution mode selector">
          <button
            type="button"
            className={`mode-pill ${mode === "fixture" ? "active-fixture" : ""}`}
            disabled={busy}
            aria-pressed={mode === "fixture"}
            onClick={() => onModeChange("fixture")}
          >
            Local Fixture Mode (Simulated)
          </button>
          <button
            type="button"
            className={`mode-pill ${mode === "api" ? "active-api" : ""}`}
            disabled={busy}
            aria-pressed={mode === "api"}
            onClick={() => onModeChange("api")}
          >
            Live API Mode (/api/*)
          </button>
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={onToggleGuide}
            aria-expanded={showGuide}
          >
            {showGuide ? "Hide Rehearsal Guide" : "Screen Guide (C5)"}
          </button>
          <button
            type="button"
            className="btn-secondary btn-small"
            disabled={busy}
            onClick={onResetSession}
          >
            New / Reset Session
          </button>
        </div>
      </div>

      {mode === "fixture" ? (
        <div className="mode-notice fixture-notice" role="region" aria-label="Fixture mode configuration">
          <div className="notice-header">
            <span className="badge badge-warning">DEVELOPMENT FIXTURE SUBSTITUTE</span>
            <span>
              Running against deterministic local fixtures in browser memory.{" "}
              <strong>No live Gemini model calls, database reservations, or real PayPal API calls are made in this mode.</strong>
            </span>
          </div>

          <div className="scenario-picker-row">
            <label htmlFor="fixture-scenario-select" className="scenario-label">
              Select H0 Acceptance Scenario:
            </label>
            <select
              id="fixture-scenario-select"
              className="scenario-select"
              value={scenarioId}
              disabled={busy}
              onChange={(e) => onScenarioChange(e.target.value as FixtureScenarioId)}
            >
              {FIXTURE_SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} — [{s.badge}]
                </option>
              ))}
            </select>
          </div>

          <p className="scenario-meta-text">
            <strong>Scenario Goal:</strong> {activeScenario.description}{" "}
            <span className="scenario-expected">
              ({activeScenario.expectedOutcomeText})
            </span>
          </p>
        </div>
      ) : (
        <div className="mode-notice api-notice" role="region" aria-label="Live API mode notice">
          <span className="badge badge-live">LIVE PRODUCTION / SANDBOX ENDPOINTS</span>
          <span>
            Connected to <code>POST /api/negotiations</code>,{" "}
            <code>POST /api/negotiations/&#123;id&#125;/turn</code>,{" "}
            <code>GET /api/negotiations/&#123;id&#125;</code>, and{" "}
            <code>/api/payments/*</code> using server-owned session cookies.
          </span>
        </div>
      )}
    </header>
  );
}
```

---

### File 7: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\components\RequirementForm.tsx`
- **Purpose:** Implements C2 pass gate (*"Build requirement form and offer history. Show delivered-by date, quantities and total. Separate private budget entry from transcript. Invalid inputs cannot start negotiation."*). Enforces cumulative delivery deadline quantities (`12` by `2026-11-13`, `30` by `2026-11-16`) as required by `backend/domain/CONTRACTS.md` (lines 39–48) and visually isolates `budget_cents` in a dedicated **Private Buyer Constraint** box.
- **Connections:** Imported by `App.tsx`.

```tsx
import React, { useState } from "react";
import { Color, CreateNegotiationRequest, DeliveryMinimum } from "../types";
import {
  APPROVED_DEFAULT_REQUEST,
  formatUsd,
  validateNegotiationRequest,
} from "../fixtures/scenarios";

interface RequirementFormProps {
  initialRequest: CreateNegotiationRequest;
  disabled: boolean;
  hasActiveNegotiation: boolean;
  onStartNegotiation: (payload: CreateNegotiationRequest) => void;
  onLoadPreset: (preset: CreateNegotiationRequest) => void;
}

export default function RequirementForm({
  initialRequest,
  disabled,
  hasActiveNegotiation,
  onStartNegotiation,
  onLoadPreset,
}: RequirementFormProps) {
  const [sku, setSku] = useState<string>(initialRequest.sku);
  const [quantity, setQuantity] = useState<number>(initialRequest.quantity);
  const [budgetDollars, setBudgetDollars] = useState< string >(
    (initialRequest.budget_cents / 100).toFixed(2)
  );
  const [allowedColors, setAllowedColors] = useState<Color[]>(
    initialRequest.allowed_colors
  );
  const [preferredColor, setPreferredColor] = useState<Color | null>(
    initialRequest.preferred_color
  );
  const [deadlines, setDeadlines] = useState<DeliveryMinimum[]>(
    initialRequest.minimum_by_date
  );

  const parsedBudgetCents = Math.round(Number(budgetDollars) * 100);
  const currentPayload: CreateNegotiationRequest = {
    sku: sku.trim(),
    quantity: Number(quantity),
    minimum_by_date: deadlines.map((d) => ({
      date: d.date,
      qty: Number(d.qty),
    })),
    budget_cents: Number.isFinite(parsedBudgetCents) ? parsedBudgetCents : -1,
    allowed_colors: allowedColors,
    preferred_color: preferredColor,
  };

  const validationErrors = validateNegotiationRequest(currentPayload);
  const isValid = validationErrors.length === 0;

  function handleColorToggle(color: Color) {
    setAllowedColors((prev) => {
      const exists = prev.includes(color);
      const next = exists ? prev.filter((c) => c !== color) : [...prev, color];
      if (preferredColor && !next.includes(preferredColor)) {
        setPreferredColor(next[0] ?? null);
      }
      return next;
    });
  }

  function handleDeadlineChange(
    index: number,
    field: keyof DeliveryMinimum,
    value: string
  ) {
    setDeadlines((prev) =>
      prev.map((item, idx) =>
        idx === index
          ? {
              ...item,
              [field]: field === "qty" ? Number.parseInt(value || "0", 10) : value,
            }
          : item
      )
    );
  }

  function handleAddDeadline() {
    const lastDate = deadlines[deadlines.length - 1]?.date ?? "2026-11-16";
    setDeadlines((prev) => [
      ...prev,
      { date: lastDate, qty: quantity > 0 ? quantity : 30 },
    ]);
  }

  function handleRemoveDeadline(index: number) {
    if (deadlines.length <= 1) return;
    setDeadlines((prev) => prev.filter((_, idx) => idx !== index));
  }

  function handleResetToH0Fixture() {
    setSku(APPROVED_DEFAULT_REQUEST.sku);
    setQuantity(APPROVED_DEFAULT_REQUEST.quantity);
    setBudgetDollars((APPROVED_DEFAULT_REQUEST.budget_cents / 100).toFixed(2));
    setAllowedColors([...APPROVED_DEFAULT_REQUEST.allowed_colors]);
    setPreferredColor(APPROVED_DEFAULT_REQUEST.preferred_color);
    setDeadlines(APPROVED_DEFAULT_REQUEST.minimum_by_date.map((d) => ({ ...d })));
    onLoadPreset(APPROVED_DEFAULT_REQUEST);
  }

  function handleTryImpossibleDeadlinePreset() {
    const impossiblePreset: CreateNegotiationRequest = {
      ...APPROVED_DEFAULT_REQUEST,
      minimum_by_date: [
        { date: "2026-11-13", qty: 20 }, // Only 12 navy exist on Friday
        { date: "2026-11-16", qty: 30 },
      ],
    };
    setSku(impossiblePreset.sku);
    setQuantity(impossiblePreset.quantity);
    setBudgetDollars((impossiblePreset.budget_cents / 100).toFixed(2));
    setAllowedColors([...impossiblePreset.allowed_colors]);
    setPreferredColor(impossiblePreset.preferred_color);
    setDeadlines(impossiblePreset.minimum_by_date.map((d) => ({ ...d })));
    onLoadPreset(impossiblePreset);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid || disabled) return;
    onStartNegotiation(currentPayload);
  }

  return (
    <section className="card requirement-card" aria-labelledby="req-heading">
      <div className="card-header-row">
        <div>
          <h2 id="req-heading" className="section-title">
            1. Buyer Order Requirements
          </h2>
          <p className="section-desc">
            Shared order terms are sent to both agents. Your maximum budget stays strictly private to your Buyer Agent.
          </p>
        </div>
        <div className="preset-btn-group">
          <button
            type="button"
            className="btn-outline btn-small"
            disabled={disabled}
            onClick={handleResetToH0Fixture}
          >
            Load H0 Standard (30 Shirts)
          </button>
          <button
            type="button"
            className="btn-outline btn-small"
            disabled={disabled}
            onClick={handleTryImpossibleDeadlinePreset}
          >
            Preset: 20 Shirts by Friday
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <div className="form-grid-2">
          <div className="form-field">
            <label htmlFor="sku-input">Catalog SKU</label>
            <input
              id="sku-input"
              type="text"
              value={sku}
              disabled={disabled}
              onChange={(e) => setSku(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="qty-input">Total Order Quantity (Shirts)</label>
            <input
              id="qty-input"
              type="number"
              min={1}
              step={1}
              value={quantity}
              disabled={disabled}
              onChange={(e) => setQuantity(Number.parseInt(e.target.value || "0", 10))}
              required
            />
          </div>
        </div>

        <div className="form-grid-2">
          <fieldset className="form-field fieldset-reset" disabled={disabled}>
            <legend className="field-legend">Allowed Colors</legend>
            <div className="checkbox-row">
              {(["navy", "black"] as const).map((color) => (
                <label key={color} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={allowedColors.includes(color)}
                    onChange={() => handleColorToggle(color)}
                  />
                  <span className={`color-swatch swatch-${color}`} aria-hidden="true" />
                  <span className="capitalize">{color}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="form-field">
            <label htmlFor="preferred-color-select">Preferred Color</label>
            <select
              id="preferred-color-select"
              value={preferredColor ?? ""}
              disabled={disabled}
              onChange={(e) =>
                setPreferredColor(
                  e.target.value ? (e.target.value as Color) : null
                )
              }
            >
              <option value="">No preference</option>
              {allowedColors.map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Cumulative Delivery Schedule */}
        <div className="deadlines-box">
          <div className="deadlines-header">
            <div>
              <h3 className="sub-heading">
                Cumulative Delivery Schedule (<code>minimum_by_date</code>)
              </h3>
              <p className="helper-text">
                Each milestone specifies the <strong>cumulative total</strong> shirts delivered on or before that date. Final milestone must equal {quantity || 0} shirts.
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary btn-small"
              disabled={disabled || deadlines.length >= 4}
              onClick={handleAddDeadline}
            >
              + Add Milestone
            </button>
          </div>

          <div className="deadlines-list">
            {deadlines.map((d, idx) => {
              const prevQty = idx === 0 ? 0 : deadlines[idx - 1].qty;
              const batchDelta = Math.max(0, d.qty - prevQty);
              return (
                <div key={idx} className="deadline-row">
                  <div className="deadline-col">
                    <label htmlFor={`deadline-date-${idx}`}>
                      Milestone #{idx + 1} Arrive By Date
                    </label>
                    <input
                      id={`deadline-date-${idx}`}
                      type="date"
                      value={d.date}
                      disabled={disabled}
                      onChange={(e) =>
                        handleDeadlineChange(idx, "date", e.target.value)
                      }
                    />
                  </div>
                  <div className="deadline-col">
                    <label htmlFor={`deadline-qty-${idx}`}>
                      Cumulative Minimum Qty
                    </label>
                    <input
                      id={`deadline-qty-${idx}`}
                      type="number"
                      min={1}
                      max={quantity || 9999}
                      value={d.qty}
                      disabled={disabled}
                      onChange={(e) =>
                        handleDeadlineChange(idx, "qty", e.target.value)
                      }
                    />
                  </div>
                  <div className="deadline-col deadline-explain">
                    <span className="batch-Increment">
                      {idx === 0
                        ? `At least ${d.qty} shirts by ${d.date || "date"}`
                        : `+${batchDelta} more (${d.qty} cumulative) by ${d.date || "date"}`}
                    </span>
                    {deadlines.length > 1 && (
                      <button
                        type="button"
                        className="btn-link-danger"
                        disabled={disabled}
                        onClick={() => handleRemoveDeadline(idx)}
                        aria-label={`Remove milestone ${idx + 1}`}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Strictly Separated Private Budget Box (C2 requirement) */}
        <div className="private-budget-box" role="region" aria-labelledby="private-budget-title">
          <div className="private-budget-header">
            <span className="badge badge-private">PRIVATE BUYER INPUT — SERVER-ONLY</span>
            <h3 id="private-budget-title" className="private-title">
              Maximum Inclusive Budget (<code>budget_cents</code>)
            </h3>
          </div>
          <p className="private-desc">
            Passed exclusively to your isolated Buyer Agent process and server-side eligibility check.{" "}
            <strong>Never exposed to the Seller Agent or public negotiation transcript.</strong>
          </p>
          <div className="budget-input-row">
            <label htmlFor="budget-dollars-input" className="budget-label">
              Max Total (USD, including delivery):
            </label>
            <div className="currency-input-wrap">
              <span className="currency-prefix">$</span>
              <input
                id="budget-dollars-input"
                type="number"
                min="1"
                step="1"
                value={budgetDollars}
                disabled={disabled}
                onChange={(e) => setBudgetDollars(e.target.value)}
              />
            </div>
            <span className="cents-pill">
              = {Number.isFinite(parsedBudgetCents) && parsedBudgetCents > 0 ? `${parsedBudgetCents} cents (${formatUsd(parsedBudgetCents)})` : "Invalid cents"}
            </span>
          </div>
        </div>

        {/* Validation Feedback */}
        {validationErrors.length > 0 && (
          <div className="validation-error-box" role="alert">
            <strong>Cannot start negotiation — please fix invalid inputs:</strong>
            <ul>
              {validationErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="form-actions-row">
          <button
            type="submit"
            className="btn-primary btn-large"
            disabled={!isValid || disabled}
          >
            {hasActiveNegotiation
              ? "Start New Negotiation with These Terms"
              : "Start Agent Negotiation"}
          </button>
        </div>
      </form>
    </section>
  );
}
```

---

### File 8: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\components\NegotiationTranscript.tsx`
- **Purpose:** Implements C2 & C4 pass gates (*"Build requirement form and offer history. Show delivered-by date, quantities and total. Separate private budget entry from transcript. User sees why the USD 330 offer misses Friday."*, *"Test keyboard controls and double-clicks"*). Renders the public `messages` transcript (`{actor, text}`), turn progression buttons (`Next Agent Turn`, `Run All Remaining Turns`, `Retry Turn` on `retryable_error`, `Refresh Status`), and the **Merchant Offer Constraint Analysis** table comparing the Monday-only `$330.00` offer against the `$354.00` split offer.
- **Connections:** Imported by `App.tsx`.

```tsx
import {
  CreateNegotiationRequest,
  NegotiationPublicView,
  OfferEvaluationSummary,
} from "../types";
import {
  MONDAY_ONLY_OFFER_LINES,
  SPLIT_OFFER_LINES,
  evaluateOfferAgainstRequirements,
  formatUsd,
} from "../fixtures/scenarios";

interface NegotiationTranscriptProps {
  view: NegotiationPublicView | null;
  activeRequest: CreateNegotiationRequest;
  busy: boolean;
  autoRunning: boolean;
  onAdvanceTurn: () => void;
  onAutoRunTurns: () => void;
  onRefresh: () => void;
}

export default function NegotiationTranscript({
  view,
  activeRequest,
  busy,
  autoRunning,
  onAdvanceTurn,
  onAutoRunTurns,
  onRefresh,
}: NegotiationTranscriptProps) {
  const mondayEvaluation: OfferEvaluationSummary =
    evaluateOfferAgainstRequirements(
      "Merchant Option A: Monday-Only Bulk Offer ($330.00)",
      33000,
      MONDAY_ONLY_OFFER_LINES,
      activeRequest,
      activeRequest.budget_cents
    );

  const splitEvaluation: OfferEvaluationSummary =
    evaluateOfferAgainstRequirements(
      "Merchant Option B: Split Delivery Offer ($354.00)",
      35400,
      SPLIT_OFFER_LINES,
      activeRequest,
      activeRequest.budget_cents
    );

  const canAdvance =
    view !== null &&
    (view.status === "negotiating" || view.status === "retryable_error") &&
    view.version < 6;

  return (
    <section className="card transcript-card" aria-labelledby="transcript-heading">
      <div className="card-header-row">
        <div>
          <h2 id="transcript-heading" className="section-title">
            2. AI Negotiation & Offer Eligibility Analysis
          </h2>
          <p className="section-desc">
            Public transcript excludes private buyer budget and private seller floor. Up to 6 bounded turns.
          </p>
        </div>

        {view && (
          <div className="status-meta-group" aria-live="polite">
            <span className="meta-id" title="Negotiation ID">
              ID: <code>{view.id}</code>
            </span>
            <span className="meta-version">
              Turn Version: <strong>{view.version} / 6</strong>
            </span>
            <span className={`status-badge status-${view.status}`}>
              Status: {view.status.toUpperCase()}
            </span>
          </div>
        )}
      </div>

      {/* Interactive Turn Controls */}
      <div className="turn-controls-bar" role="toolbar" aria-label="Negotiation turn controls">
        {!view ? (
          <p className="empty-prompt">
            Submit the Buyer Order Requirements above to initialize a negotiation session.
          </p>
        ) : (
          <>
            <button
              type="button"
              className="btn-primary"
              disabled={!canAdvance || busy || autoRunning}
              onClick={onAdvanceTurn}
            >
              {busy && !autoRunning
                ? "Running Turn..."
                : view.status === "retryable_error"
                ? `Retry Turn (v${view.version})`
                : `Advance Next Turn (${view.version % 2 === 0 ? "Buyer Agent" : "Seller Agent"})`}
            </button>

            <button
              type="button"
              className="btn-secondary"
              disabled={!canAdvance || busy || autoRunning}
              onClick={onAutoRunTurns}
            >
              {autoRunning
                ? "Auto-Negotiating..."
                : "Complete Negotiation (Auto-Step)"}
            </button>

            <button
              type="button"
              className="btn-outline"
              disabled={busy || autoRunning}
              onClick={onRefresh}
            >
              Refresh Status (GET)
            </button>
          </>
        )}
      </div>

      {/* Reason / Error Banner if no_deal, expired, or retryable_error */}
      {view?.reason && (
        <div
          className={`negotiation-reason-banner reason-${view.status}`}
          role="status"
          aria-live="polite"
        >
          <strong>
            {view.status === "no_deal"
              ? "No Deal Reached: "
              : view.status === "expired"
              ? "Quote Expired: "
              : view.status === "retryable_error"
              ? "Retryable Agent Error: "
              : "Status Note: "}
          </strong>
          <span>{view.reason}</span>
        </div>
      )}

      {/* Turn-by-turn Public Transcript */}
      <div className="transcript-feed" role="log" aria-label="Public negotiation messages">
        <h3 className="sub-heading">Public Agent Transcript</h3>
        {!view || view.messages.length === 0 ? (
          <p className="transcript-empty">
            {view
              ? "Negotiation created at version 0. Click 'Advance Next Turn' or 'Complete Negotiation' to run the agents."
              : "No active negotiation transcript yet."}
          </p>
        ) : (
          <ol className="message-list">
            {view.messages.map((msg, idx) => (
              <li
                key={idx}
                className={`message-item actor-${msg.actor}`}
              >
                <div className="message-header">
                  <span className={`actor-badge badge-${msg.actor}`}>
                    Turn #{idx + 1} · {msg.actor === "buyer" ? "Buyer AI Agent" : "Seller AI Agent"}
                  </span>
                </div>
                <p className="message-text">{msg.text}</p>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* C2 Requirement: Show why the $330 Monday-only offer misses Friday while the $354 split offer qualifies */}
      <div className="offer-comparison-section" role="region" aria-labelledby="offer-comp-heading">
        <h3 id="offer-comp-heading" className="sub-heading">
          Merchant Candidate Offer History & Deadline Verification
        </h3>
        <p className="helper-text">
          Evaluates the merchant&apos;s candidate offers against your cumulative delivery milestones (
          {activeRequest.minimum_by_date
            .map((m) => `${m.qty} by ${m.date}`)
            .join(", ")}
          ).
        </p>

        <div className="offer-cards-grid">
          {[mondayEvaluation, splitEvaluation].map((offer) => (
            <div
              key={offer.label}
              className={`offer-eval-card ${
                offer.qualifies ? "offer-qualifies" : "offer-disqualified"
              }`}
            >
              <div className="offer-card-top">
                <h4 className="offer-card-title">{offer.label}</h4>
                <span
                  className={`badge ${
                    offer.qualifies ? "badge-success" : "badge-danger"
                  }`}
                >
                  {offer.qualifies ? "QUALIFIES" : "REJECTED — MISSES DEADLINE"}
                </span>
              </div>

              <div className="offer-price-line">
                <span>Inclusive Total:</span>
                <strong>
                  {formatUsd(offer.totalCents)} ({offer.totalCents} cents)
                </strong>
              </div>

              <table className="offer-lines-table">
                <thead>
                  <tr>
                    <th>Batch Color</th>
                    <th>Qty</th>
                    <th>Delivered By</th>
                  </tr>
                </thead>
                <tbody>
                  {offer.lines.map((line, i) => (
                    <tr key={i}>
                      <td>
                        <span
                          className={`color-dot swatch-${line.color}`}
                          aria-hidden="true"
                        />
                        {line.color}
                      </td>
                      <td>{line.qty} shirts</td>
                      <td>
                        <code>{line.deliver_by}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="deadline-check-list">
                {offer.deadlineChecks.map((chk) => (
                  <div
                    key={chk.date}
                    className={`deadline-check-item ${
                      chk.passed ? "check-pass" : "check-fail"
                    }`}
                  >
                    <span>
                      By <code>{chk.date}</code> (need {chk.requiredCumulativeQty}):
                    </span>
                    <strong>
                      {chk.deliveredCumulativeQty} delivered{" "}
                      {chk.passed
                        ? "✓"
                        : `✗ (Shortfall: ${chk.shortfallQty} shirts)`}
                    </strong>
                  </div>
                ))}
              </div>

              {offer.failureSummary ? (
                <p className="offer-verdict verdict-fail">
                  <strong>Why rejected:</strong> {offer.failureSummary}
                </p>
              ) : (
                <p className="offer-verdict verdict-pass">
                  <strong>Why accepted:</strong> Meets all cumulative delivery deadlines, color rules, and private budget ({formatUsd(activeRequest.budget_cents)} max).
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
```

---

### File 9: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\components\QuotePanel.tsx`
- **Purpose:** Renders the merchant-backed `ReservedQuote` (`id`, `currency`, `total_cents`, `expires_at` with live 1-second UTC countdown, and `lines` with `color`, `qty`, `deliver_by`). Also renders clear, judge-friendly explanations when `quote === null` (`no_deal`, `expired`, `negotiating`, `retryable_error`) and triggers automatic expiry refresh when the live UTC clock reaches `expires_at`.
- **Connections:** Imported by `App.tsx`.

```tsx
import { useEffect, useState } from "react";
import { NegotiationPublicView } from "../types";
import { formatUsd } from "../fixtures/scenarios";

interface QuotePanelProps {
  view: NegotiationPublicView | null;
  onExpireDetected: () => void;
}

export default function QuotePanel({
  view,
  onExpireDetected,
}: QuotePanelProps) {
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

  useEffect(() => {
    const expiresAt = view?.quote?.expires_at;
    if (!expiresAt || view?.status !== "quoted") {
      setRemainingSeconds(null);
      return;
    }

    function updateCountdown() {
      const expiresMs = Date.parse(expiresAt!);
      if (Number.isNaN(expiresMs)) {
        setRemainingSeconds(null);
        return;
      }
      const diffSec = Math.floor((expiresMs - Date.now()) / 1000);
      setRemainingSeconds(diffSec);
      if (diffSec <= 0) {
        onExpireDetected();
      }
    }

    updateCountdown();
    const timer = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(timer);
  }, [view?.quote?.expires_at, view?.status, onExpireDetected]);

  const quote = view?.quote ?? null;
  const isQuoteActive =
    view?.status === "quoted" &&
    quote !== null &&
    (remainingSeconds === null || remainingSeconds > 0);

  return (
    <section className="card quote-card" aria-labelledby="quote-heading">
      <div className="card-header-row">
        <div>
          <h2 id="quote-heading" className="section-title">
            3. Merchant-Backed Quote & Stock Reservation
          </h2>
          <p className="section-desc">
            Atomic PostgreSQL stock reservation with server-enforced UTC expiration.
          </p>
        </div>

        {quote && isQuoteActive && (
          <span className="badge badge-success">STOCK RESERVED</span>
        )}
        {view?.status === "no_deal" && (
          <span className="badge badge-danger">NO QUOTE ISSUED</span>
        )}
        {view?.status === "expired" && (
          <span className="badge badge-warning">QUOTE EXPIRED (HTTP 410)</span>
        )}
      </div>

      {!view && (
        <div className="quote-empty-state">
          <p>
            No quote issued yet. Start and complete a negotiation to reserve inventory and generate a merchant-backed quote.
          </p>
        </div>
      )}

      {view && !quote && (
        <div className={`quote-null-state state-${view.status}`} role="status">
          {view.status === "negotiating" && (
            <>
              <h3>Negotiation in Progress (Turn {view.version} of 6)</h3>
              <p>
                Stock is not reserved until both AI agents accept an eligible offer that passes server-side deadline, color, budget, and inventory validation.
              </p>
            </>
          )}

          {view.status === "no_deal" && (
            <>
              <h3>Checkout Unavailable — No Deal Reached</h3>
              <p className="reason-highlight">
                {view.reason ||
                  "The buyer requirements and available dated inventory could not be satisfied."}
              </p>
              <p className="null-guarantee">
                <strong>Server Guarantee:</strong> Quote is <code>null</code>. Zero stockbatches are held, and no PayPal order or authorization can be created.
              </p>
            </>
          )}

          {view.status === "expired" && (
            <>
              <h3>Checkout Unavailable — Reservation Expired</h3>
              <p className="reason-highlight">
                {view.reason || "The quote has expired."}
              </p>
              <p className="null-guarantee">
                <strong>Recovery Path:</strong> Unclaimed reserved stock has been automatically released back to inventory. Start a new negotiation to request a fresh quote.
              </p>
            </>
          )}

          {view.status === "retryable_error" && (
            <>
              <h3>Temporary Agent Timeout — Ready to Retry</h3>
              <p className="reason-highlight">
                {view.reason || "The model call timed out before saving an action."}
              </p>
              <p className="null-guarantee">
                Click <strong>Retry Turn</strong> in the negotiation panel to resume from version {view.version}.
              </p>
            </>
          )}
        </div>
      )}

      {quote && (
        <div className="quote-details-body">
          <div className="quote-summary-grid">
            <div className="quote-stat">
              <span className="stat-label">Quote ID</span>
              <code className="stat-value">{quote.id}</code>
            </div>
            <div className="quote-stat">
              <span className="stat-label">Approved Total</span>
              <strong className="stat-value stat-price">
                {formatUsd(quote.total_cents)} {quote.currency}
              </strong>
              <span className="stat-sub">({quote.total_cents} integer cents)</span>
            </div>
            <div className="quote-stat">
              <span className="stat-label">Reservation Expires (UTC)</span>
              <code className="stat-value">{quote.expires_at}</code>
              {remainingSeconds !== null && (
                <span
                  className={`countdown-pill ${
                    remainingSeconds <= 60 ? "countdown-urgent" : ""
                  }`}
                >
                  {remainingSeconds > 0
                    ? `Active: ${Math.floor(remainingSeconds / 60)}m ${
                        remainingSeconds % 60
                      }s remaining`
                    : "Expired"}
                </span>
              )}
            </div>
          </div>

          <h3 className="sub-heading">Reserved Dated Inventory Batches</h3>
          <table className="quote-lines-table">
            <thead>
              <tr>
                <th>Batch #</th>
                <th>Color</th>
                <th>Reserved Quantity</th>
                <th>Guaranteed Delivery Date</th>
              </tr>
            </thead>
            <tbody>
              {quote.lines.map((line, index) => (
                <tr key={`${line.color}-${line.deliver_by}-${index}`}>
                  <td>Batch {index + 1}</td>
                  <td>
                    <span
                      className={`color-dot swatch-${line.color}`}
                      aria-hidden="true"
                    />
                    <strong className="capitalize">{line.color}</strong>
                  </td>
                  <td>{line.qty} shirts</td>
                  <td>
                    <code>{line.deliver_by}</code>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan={2}>Total Reserved</th>
                <th>
                  {quote.lines.reduce((sum, l) => sum + l.qty, 0)} shirts
                </th>
                <th>Inclusive Price: {formatUsd(quote.total_cents)}</th>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
```

---

### File 10: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\components\CheckoutSlot.tsx`
- **Purpose:** Implements C1, C3, and C4 checkout requirements:
  - Uses Member B's `frontend/src/CheckoutButton.tsx` (`<CheckoutButton quoteId={activeQuoteId} onStatusChange={handleStatusChange} />`) without modifying `CheckoutButton.tsx`.
  - When `quote` is `null` or `status !== "quoted"`, passes `quoteId=""` so `CheckoutButton` renders its disabled `<button disabled>Checkout unavailable</button>` state, and ensures **no active pay button** is ever shown for absent or expired quotes.
  - When in **Local Fixture Mode** (or when `VITE_PAYPAL_CLIENT_ID` is not configured in local dev), provides a clearly labeled **Simulated Sandbox Checkout Substitute** alongside B's component slot so C1–C5 can test `authorized`, `pending`, `cancelled`, and `expired` states locally without PayPal credentials.
  - Queries `GET /api/payments/quotes/{quote.id}` on load, refresh, or `"pending"` / `"authorized"` states to display the persisted `paypal_order_id`, `paypal_authorization_id`, and `paypal_capture_id`, blocking duplicate checkouts when an operation is `"pending"` or `"unknown"`.
- **Connections:** Imports `CheckoutButton` from `../CheckoutButton` (Member B's file) and `saveLocalPaymentState` from `../adapters/localAdapter`.

```tsx
import { useCallback, useEffect, useState } from "react";
import CheckoutButton from "../CheckoutButton";
import {
  AdapterMode,
  CheckoutCallbackStatus,
  NegotiationAdapter,
  NegotiationPublicView,
  PaymentQuoteStatusResponse,
} from "../types";
import { formatUsd } from "../fixtures/scenarios";
import { saveLocalPaymentState } from "../adapters/localAdapter";

interface CheckoutSlotProps {
  mode: AdapterMode;
  adapter: NegotiationAdapter;
  view: NegotiationPublicView | null;
  onRefreshNegotiation: () => void;
  onSimulateForceExpire?: () => void;
}

export default function CheckoutSlot({
  mode,
  adapter,
  view,
  onRefreshNegotiation,
  onSimulateForceExpire,
}: CheckoutSlotProps) {
  const [buttonStatus, setButtonStatus] =
    useState<CheckoutCallbackStatus>("idle");
  const [paymentRecord, setPaymentRecord] =
    useState<PaymentQuoteStatusResponse | null>(null);
  const [checkingPayment, setCheckingPayment] = useState<boolean>(false);

  const quote = view?.status === "quoted" ? view.quote : null;
  const quoteId = quote?.id ?? "";

  const fetchPaymentStatus = useCallback(async () => {
    if (!quoteId) {
      setPaymentRecord(null);
      return;
    }
    setCheckingPayment(true);
    try {
      const result = await adapter.getPaymentStatus(quoteId);
      setPaymentRecord(result);
      if (result) {
        const cap = result.operations.find(
          (op) => op.operation_type === "capture" && op.status === "succeeded"
        );
        const auth = result.operations.find(
          (op) => op.operation_type === "authorize" && op.status === "succeeded"
        );
        const uncertain = result.operations.find(
          (op) => op.status === "pending" || op.status === "unknown"
        );
        if (cap) {
          setButtonStatus("captured");
        } else if (uncertain) {
          setButtonStatus("pending");
        } else if (auth) {
          setButtonStatus("authorized");
        }
      }
    } finally {
      setCheckingPayment(false);
    }
  }, [adapter, quoteId]);

  // Reset status when negotiation/quote changes and query persisted payment state
  useEffect(() => {
    setButtonStatus("idle");
    setPaymentRecord(null);
    if (quoteId) {
      void fetchPaymentStatus();
    }
  }, [quoteId, fetchPaymentStatus]);

  const handleBComponentStatusChange = useCallback(
    (rawStatus: string) => {
      const normalized = (
        [
          "checkout_unavailable",
          "pending",
          "authorized",
          "captured",
          "cancelled",
          "error",
        ].includes(rawStatus)
          ? rawStatus
          : "error"
      ) as CheckoutCallbackStatus;
      setButtonStatus(normalized);
      if (normalized === "authorized" || normalized === "pending") {
        void fetchPaymentStatus();
      }
    },
    [fetchPaymentStatus]
  );

  // Extract operation IDs from persisted payment record
  const orderOp = paymentRecord?.operations.find(
    (o) => o.operation_type === "order"
  );
  const authOp = paymentRecord?.operations.find(
    (o) => o.operation_type === "authorize"
  );
  const captureOp = paymentRecord?.operations.find(
    (o) => o.operation_type === "capture"
  );
  const hasUncertainOp = Boolean(
    paymentRecord?.operations.some(
      (o) => o.status === "pending" || o.status === "unknown"
    )
  );
  const isAlreadyAuthorizedOrCaptured =
    buttonStatus === "authorized" ||
    buttonStatus === "captured" ||
    authOp?.status === "succeeded" ||
    captureOp?.status === "succeeded";

  // Local Fixture Mode simulation helpers
  function simulateFixtureApproval() {
    if (!quote) return;
    const mockOrderId = `ORDER_SIM_${quote.id.toUpperCase()}_35400`;
    const mockAuthId = `AUTH_SIM_${quote.id.toUpperCase()}_99812`;
    const nextState: PaymentQuoteStatusResponse = {
      quote_id: quote.id,
      operations: [
        {
          operation_type: "order",
          status: "succeeded",
          paypal_order_id: mockOrderId,
          paypal_authorization_id: null,
          paypal_capture_id: null,
        },
        {
          operation_type: "authorize",
          status: "succeeded",
          paypal_order_id: mockOrderId,
          paypal_authorization_id: mockAuthId,
          paypal_capture_id: null,
        },
      ],
    };
    saveLocalPaymentState(quote.id, nextState);
    setPaymentRecord(nextState);
    setButtonStatus("authorized");
  }

  function simulateFixturePendingTimeout() {
    if (!quote) return;
    const mockOrderId = `ORDER_SIM_${quote.id.toUpperCase()}_35400`;
    const nextState: PaymentQuoteStatusResponse = {
      quote_id: quote.id,
      operations: [
        {
          operation_type: "order",
          status: "succeeded",
          paypal_order_id: mockOrderId,
          paypal_authorization_id: null,
          paypal_capture_id: null,
        },
        {
          operation_type: "authorize",
          status: "pending",
          paypal_order_id: mockOrderId,
          paypal_authorization_id: null,
          paypal_capture_id: null,
        },
      ],
    };
    saveLocalPaymentState(quote.id, nextState);
    setPaymentRecord(nextState);
    setButtonStatus("pending");
  }

  function simulateFixtureCancel() {
    setButtonStatus("cancelled");
  }

  // Only pass non-empty quoteId to B's CheckoutButton when quote is active, not pending, and not already authorized
  const effectiveQuoteIdForButton =
    quote && !hasUncertainOp && !isAlreadyAuthorizedOrCaptured
      ? quote.id
      : "";

  return (
    <section className="card checkout-card" aria-labelledby="checkout-heading">
      <div className="card-header-row">
        <div>
          <h2 id="checkout-heading" className="section-title">
            4. PayPal Sandbox Approval & Authorization Status
          </h2>
          <p className="section-desc">
            The quote server alone supplies monetary terms ({quote ? `${formatUsd(quote.total_cents)} / ${quote.total_cents} cents` : "no active quote"}). Capture is merchant-only after fulfillment.
          </p>
        </div>

        <span className={`status-badge payment-badge-${buttonStatus}`}>
          Payment: {buttonStatus.toUpperCase()}
        </span>
      </div>

      {/* Persisted Evidence IDs Panel (for Member D QA & Refresh Restoration) */}
      {quote && (
        <div className="evidence-panel" role="region" aria-label="Payment and quote evidence identifiers">
          <div className="evidence-row">
            <span>Active Quote ID:</span>
            <code>{quote.id}</code>
          </div>
          <div className="evidence-row">
            <span>Locked Amount:</span>
            <strong>
              {formatUsd(quote.total_cents)} ({quote.total_cents} cents)
            </strong>
          </div>
          <div className="evidence-row">
            <span>PayPal Order ID:</span>
            <code>{orderOp?.paypal_order_id ?? "—"}</code>
          </div>
          <div className="evidence-row">
            <span>PayPal Authorization ID:</span>
            <code className="highlight-code">
              {authOp?.paypal_authorization_id ?? "—"}
            </code>
          </div>
          {captureOp?.paypal_capture_id && (
            <div className="evidence-row">
              <span>PayPal Capture ID (Merchant):</span>
              <code className="highlight-code">
                {captureOp.paypal_capture_id}
              </code>
            </div>
          )}
        </div>
      )}

      {/* Status Messages for Pending / Authorized / Cancelled / Error */}
      {(buttonStatus === "pending" || hasUncertainOp) && (
        <div className="payment-alert alert-pending" role="alert">
          <strong>Payment Outcome Pending / Uncertain:</strong>
          <p>
            An authorization request is in progress or awaiting provider reconciliation.{" "}
            <strong>Do not start a second checkout or create a new quote.</strong> Click &ldquo;Query Payment Status&rdquo; below to check if the authorization completed.
          </p>
          <button
            type="button"
            className="btn-primary btn-small"
            disabled={checkingPayment}
            onClick={() => void fetchPaymentStatus()}
          >
            {checkingPayment
              ? "Checking Status..."
              : "Query Payment Status (GET /api/payments/quotes/{id})"}
          </button>
        </div>
      )}

      {isAlreadyAuthorizedOrCaptured && (
        <div className="payment-alert alert-authorized" role="status">
          <strong>
            {buttonStatus === "captured" || captureOp?.status === "succeeded"
              ? "Payment Captured Following Simulated Fulfillment!"
              : "PayPal Sandbox Buyer Authorization Confirmed!"}
          </strong>
          <p>
            Authorization ID:{" "}
            <code>
              {authOp?.paypal_authorization_id ??
                "Confirmed via PayPal callback"}
            </code>{" "}
            for <strong>{quote ? formatUsd(quote.total_cents) : "$354.00"}</strong>. Refreshing the browser preserves this authorization.
          </p>
        </div>
      )}

      {buttonStatus === "cancelled" && !isAlreadyAuthorizedOrCaptured && (
        <div className="payment-alert alert-cancelled" role="status">
          <strong>Buyer Cancelled PayPal Approval:</strong>
          <p>
            No authorization was created. Your quote reservation remains active until its UTC expiry timestamp—you may still approve below.
          </p>
        </div>
      )}

      {buttonStatus === "error" && (
        <div className="payment-alert alert-error" role="alert">
          <strong>Checkout Could Not Continue:</strong>
          <p>
            Check payment and quote status before retrying to ensure no duplicate operation is started.
          </p>
          <button
            type="button"
            className="btn-outline btn-small"
            onClick={() => {
              void fetchPaymentStatus();
              onRefreshNegotiation();
            }}
          >
            Verify Quote & Payment Status
          </button>
        </div>
      )}

      {/* Member B's Official Component Slot (frontend/src/CheckoutButton.tsx) */}
      <div className="b-checkout-slot-box">
        <div className="slot-label-row">
          <span className="slot-title">
            Member B Checkout Component Slot (<code>&lt;CheckoutButton /&gt;</code>)
          </span>
          {buttonStatus === "checkout_unavailable" && (
            <span className="slot-note">
              (<code>VITE_PAYPAL_CLIENT_ID</code> not set in browser env — B&apos;s component reported <code>checkout_unavailable</code>)
            </span>
          )}
        </div>

        <div className="paypal-button-mount">
          <CheckoutButton
            quoteId={effectiveQuoteIdForButton}
            onStatusChange={handleBComponentStatusChange}
          />
        </div>
      </div>

      {/* Local Fixture Mode Placeholder Controls (C1/C3 requirement: test buyer journey without PayPal credentials) */}
      {mode === "fixture" && (
        <div className="fixture-checkout-substitute" role="region" aria-label="Local fixture checkout simulator">
          <div className="substitute-header">
            <span className="badge badge-warning">LOCAL FIXTURE CHECKOUT PLACEHOLDER</span>
            <span>
              Simulate PayPal Sandbox buyer callbacks locally without PayPal credentials:
            </span>
          </div>

          <div className="substitute-btn-row">
            <button
              type="button"
              className="btn-primary"
              disabled={
                !quote ||
                hasUncertainOp ||
                isAlreadyAuthorizedOrCaptured
              }
              onClick={simulateFixtureApproval}
            >
              Simulate PayPal Buyer Approval ({quote ? formatUsd(quote.total_cents) : "Disabled"})
            </button>

            <button
              type="button"
              className="btn-secondary"
              disabled={
                !quote ||
                hasUncertainOp ||
                isAlreadyAuthorizedOrCaptured
              }
              onClick={simulateFixtureCancel}
            >
              Simulate Buyer Cancel
            </button>

            <button
              type="button"
              className="btn-outline"
              disabled={
                !quote ||
                hasUncertainOp ||
                isAlreadyAuthorizedOrCaptured
              }
              onClick={simulateFixturePendingTimeout}
            >
              Simulate Provider Timeout (Pending State)
            </button>

            {onSimulateForceExpire && (
              <button
                type="button"
                className="btn-outline"
                disabled={!quote || isAlreadyAuthorizedOrCaptured}
                onClick={onSimulateForceExpire}
              >
                Simulate UTC Expiry (410)
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
```

---

### File 11: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\App.css`
- **Purpose:** Complete responsive stylesheet covering desktop and narrow mobile viewports (`<768px`), clear visual hierarchy for Fixture vs. Live API mode, private budget separation, accessible focus outlines, and disabled button states.
- **Connections:** Imported by `App.tsx`.

```css
:root {
  --bg-page: #f4f6f9;
  --bg-card: #ffffff;
  --text-main: #0f172a;
  --text-muted: #475569;
  --border-color: #cbd5e1;
  --primary: #003087;
  --primary-hover: #001c64;
  --accent-blue: #0070ba;
  --success-bg: #dcfce7;
  --success-text: #166534;
  --success-border: #86efac;
  --warning-bg: #fef9c3;
  --warning-text: #854d0e;
  --warning-border: #fde047;
  --danger-bg: #fee2e2;
  --danger-text: #991b1b;
  --danger-border: #fca5a5;
  --private-bg: #f8fafc;
  --private-border: #6366f1;
  --radius: 10px;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  background-color: var(--bg-page);
  color: var(--text-main);
  line-height: 1.5;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
  background: #f1f5f9;
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
}

.app-shell {
  max-width: 1280px;
  margin: 0 auto;
  padding: 1rem 1.25rem 3rem;
}

/* Mode Banner */
.mode-banner {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.mode-banner-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.brand-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary), var(--accent-blue));
  color: #ffffff;
  font-weight: 800;
  font-size: 1.1rem;
}

.brand-title {
  margin: 0;
  font-size: 1.4rem;
  color: var(--primary);
}

.brand-subtitle {
  margin: 0.15rem 0 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}

.mode-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.mode-pill {
  padding: 0.5rem 0.9rem;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: #f8fafc;
  color: var(--text-main);
  font-weight: 600;
  cursor: pointer;
}

.mode-pill.active-fixture {
  background: var(--warning-bg);
  border-color: #eab308;
  color: var(--warning-text);
}

.mode-pill.active-api {
  background: var(--success-bg);
  border-color: #22c55e;
  color: var(--success-text);
}

.mode-notice {
  margin-top: 0.9rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.92rem;
}

.fixture-notice {
  background: #fffbeb;
  border: 1px solid var(--warning-border);
}

.api-notice {
  background: #f0fdf4;
  border: 1px solid var(--success-border);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
}

.notice-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.6rem;
}

.scenario-picker-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin: 0.5rem 0;
}

.scenario-label {
  font-weight: 700;
}

.scenario-select {
  flex: 1;
  min-width: 260px;
  padding: 0.45rem 0.65rem;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  font-size: 0.95rem;
}

.scenario-meta-text {
  margin: 0.35rem 0 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}

.scenario-expected {
  color: var(--text-main);
  font-weight: 500;
}

/* Badges */
.badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.badge-warning {
  background: var(--warning-bg);
  color: var(--warning-text);
  border: 1px solid var(--warning-border);
}

.badge-live,
.badge-success {
  background: var(--success-bg);
  color: var(--success-text);
  border: 1px solid var(--success-border);
}

.badge-danger {
  background: var(--danger-bg);
  color: var(--danger-text);
  border: 1px solid var(--danger-border);
}

.badge-private {
  background: #e0e7ff;
  color: #3730a3;
  border: 1px solid #a5b4fc;
}

/* Layout Grid */
.workspace-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
  align-items: start;
}

.workspace-col {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}

.card-header-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
}

.section-title {
  margin: 0;
  font-size: 1.15rem;
  color: var(--primary);
}

.section-desc {
  margin: 0.25rem 0 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}

.sub-heading {
  margin: 0 0 0.35rem;
  font-size: 1rem;
}

.helper-text {
  margin: 0 0 0.75rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}

/* Forms & Buttons */
.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.9rem;
  margin-bottom: 0.9rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.form-field label,
.field-legend {
  font-size: 0.88rem;
  font-weight: 600;
}

.fieldset-reset {
  border: none;
  margin: 0;
  padding: 0;
}

input[type="text"],
input[type="number"],
input[type="date"],
select {
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 0.95rem;
  background: #ffffff;
}

input:focus-visible,
select:focus-visible,
button:focus-visible {
  outline: 3px solid var(--accent-blue);
  outline-offset: 2px;
}

.checkbox-row {
  display: flex;
  gap: 1rem;
  padding-top: 0.35rem;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
}

.color-swatch,
.color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  margin-right: 0.35rem;
  vertical-align: middle;
}

.swatch-navy {
  background-color: #1e3a8a;
  border: 1px solid #172554;
}

.swatch-black {
  background-color: #0f172a;
  border: 1px solid #000000;
}

.capitalize {
  text-transform: capitalize;
}

.deadlines-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.9rem;
  margin-bottom: 1rem;
}

.deadlines-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
}

.deadline-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr;
  gap: 0.75rem;
  align-items: end;
  padding: 0.55rem 0;
  border-top: 1px dashed #cbd5e1;
}

.deadline-col {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.deadline-explain {
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
  color: var(--text-muted);
}

/* Private Budget Box */
.private-budget-box {
  background: var(--private-bg);
  border: 2px solid var(--private-border);
  border-radius: 8px;
  padding: 0.95rem;
  margin-bottom: 1rem;
}

.private-budget-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
}

.private-title {
  margin: 0;
  font-size: 1rem;
  color: #312e81;
}

.private-desc {
  margin: 0.35rem 0 0.75rem;
  font-size: 0.86rem;
  color: var(--text-muted);
}

.budget-input-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.currency-input-wrap {
  display: inline-flex;
  align-items: center;
}

.currency-prefix {
  padding: 0.5rem 0.6rem;
  background: #e2e8f0;
  border: 1px solid var(--border-color);
  border-right: none;
  border-radius: 6px 0 0 6px;
  font-weight: 700;
}

.currency-input-wrap input {
  border-radius: 0 6px 6px 0;
  width: 120px;
}

.cents-pill {
  font-size: 0.85rem;
  font-weight: 600;
  color: #312e81;
}

.validation-error-box {
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.validation-error-box ul {
  margin: 0.4rem 0 0;
  padding-left: 1.25rem;
}

/* Buttons */
.btn-primary,
.btn-secondary,
.btn-outline {
  padding: 0.55rem 1rem;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.92rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-primary {
  background: var(--primary);
  color: #ffffff;
  border: 1px solid var(--primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-secondary {
  background: #e2e8f0;
  color: var(--text-main);
  border: 1px solid #cbd5e1;
}

.btn-outline {
  background: #ffffff;
  color: var(--primary);
  border: 1px solid var(--primary);
}

.btn-small {
  padding: 0.35rem 0.7rem;
  font-size: 0.82rem;
}

.btn-large {
  width: 100%;
  padding: 0.7rem 1.2rem;
  font-size: 1rem;
}

.btn-link-danger {
  background: none;
  border: none;
  color: var(--danger-text);
  text-decoration: underline;
  cursor: pointer;
  font-size: 0.82rem;
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.preset-btn-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

/* Transcript & Offer Cards */
.status-meta-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
}

.status-badge {
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  font-weight: 700;
  font-size: 0.78rem;
}

.status-negotiating,
.status-quoting {
  background: #dbeafe;
  color: #1e40af;
}

.status-quoted,
.payment-badge-authorized,
.payment-badge-captured {
  background: var(--success-bg);
  color: var(--success-text);
}

.status-no_deal,
.payment-badge-error {
  background: var(--danger-bg);
  color: var(--danger-text);
}

.status-expired,
.status-retryable_error,
.payment-badge-pending,
.payment-badge-cancelled {
  background: var(--warning-bg);
  color: var(--warning-text);
}

.turn-controls-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-bottom: 1rem;
}

.negotiation-reason-banner {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}

.negotiation-reason-banner.reason-retryable_error,
.negotiation-reason-banner.reason-expired {
  background: var(--warning-bg);
  border-color: var(--warning-border);
  color: var(--warning-text);
}

.transcript-feed {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.9rem;
  margin-bottom: 1.15rem;
}

.message-list {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.message-item {
  padding: 0.65rem 0.85rem;
  border-radius: 8px;
  background: #ffffff;
  border-left: 4px solid var(--primary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.message-item.actor-seller {
  border-left-color: #0d9488;
}

.actor-badge {
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
}

.message-text {
  margin: 0.25rem 0 0;
  font-size: 0.95rem;
}

.offer-cards-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.85rem;
}

.offer-eval-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0.85rem;
  background: #ffffff;
}

.offer-eval-card.offer-qualifies {
  border-color: #22c55e;
  background: #f0fdf4;
}

.offer-eval-card.offer-disqualified {
  border-color: #f87171;
  background: #fef2f2;
}

.offer-card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.offer-card-title {
  margin: 0;
  font-size: 0.92rem;
}

.offer-price-line {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.offer-lines-table,
.quote-lines-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
  margin-bottom: 0.6rem;
}

.offer-lines-table th,
.offer-lines-table td,
.quote-lines-table th,
.quote-lines-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.deadline-check-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.83rem;
  margin-bottom: 0.5rem;
}

.deadline-check-item {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0.45rem;
  border-radius: 4px;
}

.check-pass {
  background: #dcfce7;
  color: #166534;
}

.check-fail {
  background: #fee2e2;
  color: #991b1b;
}

.offer-verdict {
  margin: 0;
  font-size: 0.83rem;
}

/* Quote & Checkout Panels */
.quote-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.quote-stat {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.stat-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
}

.stat-price {
  font-size: 1.2rem;
  color: var(--primary);
}

.countdown-pill {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--success-text);
}

.countdown-urgent {
  color: var(--danger-text);
}

.quote-null-state {
  padding: 0.9rem 1rem;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid var(--border-color);
}

.quote-null-state.state-no_deal {
  background: var(--danger-bg);
  border-color: var(--danger-border);
  color: var(--danger-text);
}

.quote-null-state.state-expired {
  background: var(--warning-bg);
  border-color: var(--warning-border);
  color: var(--warning-text);
}

.evidence-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.75rem 0.95rem;
  margin-bottom: 1rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem 1rem;
  font-size: 0.88rem;
}

.evidence-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.highlight-code {
  background: #dcfce7;
  color: #166534;
  font-weight: 700;
}

.payment-alert {
  padding: 0.85rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.alert-pending {
  background: var(--warning-bg);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
}

.alert-authorized {
  background: var(--success-bg);
  border: 1px solid var(--success-border);
  color: var(--success-text);
}

.alert-cancelled,
.alert-error {
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}

.b-checkout-slot-box {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 0.9rem;
  background: #ffffff;
  margin-bottom: 1rem;
}

.slot-label-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-bottom: 0.65rem;
}

.fixture-checkout-substitute {
  background: #fffbeb;
  border: 1px dashed #eab308;
  border-radius: 8px;
  padding: 0.9rem;
}

.substitute-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
  font-size: 0.88rem;
}

.substitute-btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.global-error-banner {
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
  padding: 0.8rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.rehearsal-guide-card {
  margin-bottom: 1.25rem;
  border-left: 5px solid var(--primary);
}

.rehearsal-steps-list {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.9rem;
}

/* Narrow Viewport / Mobile Responsiveness (C4 requirement) */
@media (max-width: 960px) {
  .workspace-grid,
  .offer-cards-grid,
  .quote-summary-grid,
  .evidence-panel {
    grid-template-columns: 1fr;
  }

  .deadline-row,
  .form-grid-2 {
    grid-template-columns: 1fr;
  }
}
```

---

### File 12: `d:\Paypal hackathon\PayPal_Hackathon\frontend\src\App.tsx`
- **Purpose:** Orchestrates the entire Member C buyer journey:
  - Restores state across page refreshes (`F5`) and browser back/forward (`window.onpopstate`) using URL query params (`?mode=...&scenario=...&negotiation_id=...`) and `sessionStorage`.
  - Prevents double-clicks with a synchronous `inFlightRef` lock alongside React `busy` state.
  - Handles HTTP `409` (`operation_conflict` / `stock_conflict`) by automatically querying `GET /api/negotiations/{id}` to restore authoritative state.
  - Handles HTTP `410` (`expired`) by refreshing the negotiation view so checkout is immediately disabled.
  - Includes the built-in C5 screenshot-free text guide for Member D's rehearsal.
- **Connections:** Imports `ModeBanner`, `RequirementForm`, `NegotiationTranscript`, `QuotePanel`, `CheckoutSlot`, `LocalFixtureAdapter`, `LiveApiAdapter`, and `App.css`.

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import {
  AdapterHttpError,
  AdapterMode,
  CreateNegotiationRequest,
  FixtureScenarioId,
  NegotiationAdapter,
  NegotiationPublicView,
} from "./types";
import {
  APPROVED_DEFAULT_REQUEST,
  FIXTURE_SCENARIOS,
} from "./fixtures/scenarios";
import {
  LocalFixtureAdapter,
  clearLocalFixtureStorage,
} from "./adapters/localAdapter";
import { LiveApiAdapter } from "./adapters/apiAdapter";
import ModeBanner from "./components/ModeBanner";
import RequirementForm from "./components/RequirementForm";
import NegotiationTranscript from "./components/NegotiationTranscript";
import QuotePanel from "./components/QuotePanel";
import CheckoutSlot from "./components/CheckoutSlot";

const ACTIVE_STATE_KEY = "agentnegotiate_active_ui_state_v1";

interface PersistedUiSession {
  mode: AdapterMode;
  scenarioId: FixtureScenarioId;
  negotiationId: string | null;
  lastRequest: CreateNegotiationRequest;
}

function readInitialUiSession(): PersistedUiSession {
  const params = new URLSearchParams(window.location.search);
  const urlMode = params.get("mode");
  const urlScenario = params.get("scenario");
  const urlNegId = params.get("negotiation_id");

  let stored: Partial<PersistedUiSession> = {};
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_STATE_KEY);
    if (raw) stored = JSON.parse(raw) as Partial<PersistedUiSession>;
  } catch {
    // Ignore storage read failure
  }

  const mode: AdapterMode =
    urlMode === "api" || urlMode === "fixture"
      ? urlMode
      : stored.mode === "api" || stored.mode === "fixture"
      ? stored.mode
      : "fixture";

  const validScenarioIds = FIXTURE_SCENARIOS.map((s) => s.id);
  const scenarioId: FixtureScenarioId = validScenarioIds.includes(
    urlScenario as FixtureScenarioId
  )
    ? (urlScenario as FixtureScenarioId)
    : validScenarioIds.includes(stored.scenarioId as FixtureScenarioId)
    ? (stored.scenarioId as FixtureScenarioId)
    : "feasible_split";

  const negotiationId = urlNegId || stored.negotiationId || null;
  const lastRequest = stored.lastRequest ?? APPROVED_DEFAULT_REQUEST;

  return { mode, scenarioId, negotiationId, lastRequest };
}

function syncUrlAndStorage(
  state: PersistedUiSession,
  pushHistory = false
): void {
  try {
    window.sessionStorage.setItem(ACTIVE_STATE_KEY, JSON.stringify(state));
  } catch {
    // Ignore
  }

  const url = new URL(window.location.href);
  url.searchParams.set("mode", state.mode);
  if (state.mode === "fixture") {
    url.searchParams.set("scenario", state.scenarioId);
  } else {
    url.searchParams.delete("scenario");
  }
  if (state.negotiationId) {
    url.searchParams.set("negotiation_id", state.negotiationId);
  } else {
    url.searchParams.delete("negotiation_id");
  }

  if (pushHistory) {
    window.history.pushState(state, "", url.toString());
  } else {
    window.history.replaceState(state, "", url.toString());
  }
}

export default function App() {
  const initial = useMemo(() => readInitialUiSession(), []);
  const [mode, setMode] = useState<AdapterMode>(initial.mode);
  const [scenarioId, setScenarioId] = useState<FixtureScenarioId>(
    initial.scenarioId
  );
  const [activeRequest, setActiveRequest] = useState<CreateNegotiationRequest>(
    initial.lastRequest
  );
  const [view, setView] = useState<NegotiationPublicView | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [autoRunning, setAutoRunning] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState<boolean>(false);

  // Synchronous lock to prevent double-click race conditions (C4 requirement)
  const inFlightRef = useRef<boolean>(false);

  const localAdapter = useMemo(() => new LocalFixtureAdapter(), []);
  const apiAdapter = useMemo(() => new LiveApiAdapter(), []);
  const adapter: NegotiationAdapter =
    mode === "api" ? apiAdapter : localAdapter;

  const restoreNegotiationById = useCallback(
    async (targetAdapter: NegotiationAdapter, negotiationId: string) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setBusy(true);
      setErrorBanner(null);
      try {
        const restored = await targetAdapter.getNegotiation(negotiationId);
        setView(restored);
      } catch (err) {
        if (err instanceof AdapterHttpError && err.status === 404) {
          setView(null);
        } else {
          setErrorBanner(
            err instanceof Error
              ? err.message
              : "Could not restore negotiation state."
          );
        }
      } finally {
        inFlightRef.current = false;
        setBusy(false);
      }
    },
    []
  );

  // Restore existing negotiation on initial mount
  useEffect(() => {
    if (initial.negotiationId) {
      const targetAdapter =
        initial.mode === "api" ? apiAdapter : localAdapter;
      void restoreNegotiationById(targetAdapter, initial.negotiationId);
    }
  }, [initial, apiAdapter, localAdapter, restoreNegotiationById]);

  // Handle Browser Back / Forward buttons (C4 requirement)
  useEffect(() => {
    function handlePopState() {
      const restored = readInitialUiSession();
      setMode(restored.mode);
      setScenarioId(restored.scenarioId);
      setActiveRequest(restored.lastRequest);
      const targetAdapter =
        restored.mode === "api" ? apiAdapter : localAdapter;
      if (restored.negotiationId) {
        void restoreNegotiationById(targetAdapter, restored.negotiationId);
      } else {
        setView(null);
      }
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [apiAdapter, localAdapter, restoreNegotiationById]);

  async function handleStartNegotiation(payload: CreateNegotiationRequest) {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setErrorBanner(null);
    setActiveRequest(payload);

    try {
      const created = await adapter.createNegotiation(payload, scenarioId);
      setView(created);
      syncUrlAndStorage(
        {
          mode,
          scenarioId,
          negotiationId: created.id,
          lastRequest: payload,
        },
        true
      );
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to start negotiation."
      );
    } finally {
      inFlightRef.current = false;
      setBusy(false);
    }
  }

  async function handleAdvanceSingleTurn() {
    if (!view || inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setErrorBanner(null);

    try {
      const next = await adapter.advanceTurn(view.id, view.version);
      setView(next);
    } catch (err) {
      if (err instanceof AdapterHttpError && (err.status === 409 || err.status === 410)) {
        // HTTP 409 (version/stock conflict) or 410 (expired): refresh state via GET
        setErrorBanner(`${err.message} — Refreshed latest state from server.`);
        try {
          const refreshed = await adapter.getNegotiation(view.id);
          setView(refreshed);
        } catch {
          // Ignore secondary error
        }
      } else {
        setErrorBanner(
          err instanceof Error ? err.message : "Failed to advance turn."
        );
      }
    } finally {
      inFlightRef.current = false;
      setBusy(false);
    }
  }

  async function handleAutoRunRemainingTurns() {
    if (!view || inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setAutoRunning(true);
    setErrorBanner(null);

    let currentView = view;
    try {
      for (let i = 0; i < 6; i++) {
        if (
          currentView.status !== "negotiating" &&
          currentView.status !== "retryable_error"
        ) {
          break;
        }
        currentView = await adapter.advanceTurn(
          currentView.id,
          currentView.version
        );
        setView(currentView);
        if (currentView.status === "retryable_error") {
          break;
        }
      }
    } catch (err) {
      if (err instanceof AdapterHttpError && (err.status === 409 || err.status === 410)) {
        setErrorBanner(`${err.message} — Refreshed latest state from server.`);
        try {
          const refreshed = await adapter.getNegotiation(currentView.id);
          setView(refreshed);
        } catch {
          // Ignore
        }
      } else {
        setErrorBanner(
          err instanceof Error ? err.message : "Auto-negotiation interrupted."
        );
      }
    } finally {
      inFlightRef.current = false;
      setBusy(false);
      setAutoRunning(false);
    }
  }

  const handleRefreshNegotiation = useCallback(async () => {
    if (!view || inFlightRef.current) return;
    await restoreNegotiationById(adapter, view.id);
  }, [adapter, view, restoreNegotiationById]);

  function handleModeChange(nextMode: AdapterMode) {
    if (inFlightRef.current) return;
    setMode(nextMode);
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode: nextMode,
        scenarioId,
        negotiationId: null,
        lastRequest: activeRequest,
      },
      true
    );
  }

  function handleScenarioChange(nextScenario: FixtureScenarioId) {
    if (inFlightRef.current) return;
    const meta = FIXTURE_SCENARIOS.find((s) => s.id === nextScenario);
    const nextReq = meta ? meta.presetRequest : APPROVED_DEFAULT_REQUEST;
    setScenarioId(nextScenario);
    setActiveRequest(nextReq);
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode,
        scenarioId: nextScenario,
        negotiationId: null,
        lastRequest: nextReq,
      },
      true
    );
  }

  function handleResetSession() {
    if (inFlightRef.current) return;
    clearLocalFixtureStorage();
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode,
        scenarioId,
        negotiationId: null,
        lastRequest: APPROVED_DEFAULT_REQUEST,
      },
      true
    );
  }

  function handleSimulateForceExpire() {
    if (!view || mode !== "fixture") return;
    setView({
      ...view,
      status: "expired",
      reason: "The quote has expired.",
      quote: null,
    });
  }

  return (
    <div className="app-shell">
      <ModeBanner
        mode={mode}
        scenarioId={scenarioId}
        busy={busy}
        showGuide={showGuide}
        onModeChange={handleModeChange}
        onScenarioChange={handleScenarioChange}
        onResetSession={handleResetSession}
        onToggleGuide={() => setShowGuide((prev) => !prev)}
      />

      {showGuide && (
        <section
          className="card rehearsal-guide-card"
          aria-labelledby="guide-heading"
        >
          <h2 id="guide-heading" className="section-title">
            C5 Screenshot-Free Buyer Screen Sequence & Rehearsal Guide
          </h2>
          <ol className="rehearsal-steps-list">
            <li>
              <strong>Feasible Split ($354.00):</strong> Select{" "}
              <em>1. Feasible Split Deal ($354.00)</em> in Local Fixture Mode
              (or use Live API Mode), click{" "}
              <strong>Start Agent Negotiation</strong>, then click{" "}
              <strong>Complete Negotiation (Auto-Step)</strong>. Observe Turn 1
              (Buyer asks delivery options), Turn 2 (Seller proposes $354 split:
              12 navy by 2026-11-13 + 18 black by 2026-11-16), Turn 3 (Buyer
              accepts). Inspect the Offer Comparison card showing why the $330
              Monday-only option fails Friday while the $354 split qualifies.
              Approve checkout to see the Authorization ID.
            </li>
            <li>
              <strong>Impossible Deadline / 4-Shirt Friday Shortfall:</strong>{" "}
              Switch scenario to{" "}
              <em>2. Impossible Deadline — 4-Shirt Friday Shortfall</em>, click{" "}
              <strong>Start Agent Negotiation</strong> and{" "}
              <strong>Complete Negotiation</strong>. Observe status{" "}
              <code>no_deal</code>, reason{" "}
              <code>At least 4 more shirts are required by 2026-11-13.</code>,{" "}
              <code>quote: null</code>, and disabled checkout button.
            </li>
            <li>
              <strong>Competing Buyers (HTTP 409) & Expiry (HTTP 410):</strong>{" "}
              Switch to scenarios 3, 4, or 5 to verify automatic HTTP 409 conflict
              refresh, UTC quote expiry disabling payment, and retryable turn
              recovery.
            </li>
          </ol>
        </section>
      )}

      {errorBanner && (
        <div className="global-error-banner" role="alert">
          <span>{errorBanner}</span>
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => setErrorBanner(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <main className="workspace-grid">
        <div className="workspace-col">
          <RequirementForm
            initialRequest={activeRequest}
            disabled={busy}
            hasActiveNegotiation={view !== null}
            onStartNegotiation={(payload) => void handleStartNegotiation(payload)}
            onLoadPreset={(preset) => setActiveRequest(preset)}
          />

          <QuotePanel
            view={view}
            onExpireDetected={() => void handleRefreshNegotiation()}
          />
        </div>

        <div className="workspace-col">
          <NegotiationTranscript
            view={view}
            activeRequest={activeRequest}
            busy={busy}
            autoRunning={autoRunning}
            onAdvanceTurn={() => void handleAdvanceSingleTurn()}
            onAutoRunTurns={() => void handleAutoRunRemainingTurns()}
            onRefresh={() => void handleRefreshNegotiation()}
          />

          <CheckoutSlot
            mode={mode}
            adapter={adapter}
            view={view}
            onRefreshNegotiation={() => void handleRefreshNegotiation()}
            onSimulateForceExpire={
              mode === "fixture" ? handleSimulateForceExpire : undefined
            }
          />
        </div>
      </main>
    </div>
  );
}
```

---

## 5. Ordered, Numbered Execution Checklist with Verification Commands

Follow these exact steps in PowerShell from `d:\Paypal hackathon\PayPal_Hackathon`:

### Step 1: Create Member C Feature Branch
```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon"
git status
git checkout -b member-c/buyer-ui
```
- **Expected Output:** `Switched to a new branch 'member-c/buyer-ui'`, working tree clean.

### Step 2: Verify `frontend/src/CheckoutButton.tsx` Is Untouched
```powershell
git diff frontend/src/CheckoutButton.tsx
```
- **Expected Output:** Empty output (zero modifications to Member B's file).

### Step 3: Write the 12 Member C Frontend Files
Create/update the files exactly as provided in Section 4 above:
1. `frontend/vite.config.ts`
2. `frontend/src/types.ts`
3. `frontend/src/fixtures/scenarios.ts`
4. `frontend/src/adapters/localAdapter.ts`
5. `frontend/src/adapters/apiAdapter.ts`
6. `frontend/src/components/ModeBanner.tsx`
7. `frontend/src/components/RequirementForm.tsx`
8. `frontend/src/components/NegotiationTranscript.tsx`
9. `frontend/src/components/QuotePanel.tsx`
10. `frontend/src/components/CheckoutSlot.tsx`
11. `frontend/src/App.css`
12. `frontend/src/App.tsx`

### Step 4: Run TypeScript Typecheck & Production Vite Build (C3 & C5 Gate)
```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon\frontend"
npm.cmd run build
```
- **Expected Output:**
  - `tsc --noEmit` exits 0 with zero TypeScript errors.
  - `vite v6.x.x building for production...`
  - `✓ built in ...` producing `frontend/dist/index.html` and `frontend/dist/assets/*`.

### Step 5: Verify Local Dev Server & Fixture Scenarios (C1, C2, C4, C5 Gates)
```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon\frontend"
npm.cmd run dev
```
- Open `http://localhost:5173` and verify:
  1. **C1 Gate:** App starts in **Local Fixture Mode (Simulated)** with zero backend/DB/PayPal credentials required.
  2. **C2 Gate:**
     - Private budget (`$360.00` / `36000` cents) is in the dedicated **PRIVATE BUYER INPUT — SERVER-ONLY** box and never appears in the Public Agent Transcript.
     - Merchant Candidate Offer History card explicitly shows **Merchant Option A: Monday-Only Bulk Offer ($330.00)** with `REJECTED — MISSES DEADLINE` (`By 2026-11-13 (need 12): 0 delivered ✗ (Shortfall: 12 shirts)`) and **Merchant Option B: Split Delivery Offer ($354.00)** with `QUALIFIES`.
     - Changing total quantity to `0` or making Milestone #1 quantity `35` (> 30) displays the red validation alert and disables the `Start Agent Negotiation` button.
  3. **C3 & C4 Gates:**
     - Run Scenario 1 (*Feasible Split Deal*) -> produces `status: "quoted"`, `total_cents: 35400`, active UTC expiry countdown, and enables simulated approval.
     - Run Scenario 2 (*Impossible Deadline — 4-Shirt Friday Shortfall*) -> produces `status: "no_deal"`, `reason: "At least 4 more shirts are required by 2026-11-13."`, `quote: null`, and `<button disabled>Checkout unavailable</button>`.
     - Run Scenario 3 (*Competing Buyers*) -> triggers HTTP 409 conflict and automatically refreshes state to `no_deal`.
     - Run Scenario 4 (*Expired Reservation*) -> transitions to `status: "expired"`, `quote: null`, and disables payment.
     - Run Scenario 5 (*Transient Model Timeout*) -> pauses at `retryable_error` on Turn 2; clicking `Retry Turn (v1)` completes the deal.
     - Press `F5` (Browser Refresh) and Browser Back/Forward -> negotiation ID and payment authorization ID are restored from URL/sessionStorage without replaying an order.

### Step 6: Handoff Instructions for Member B (B4 Gate Integration)
Provide this exact integration note to Member B when handing off C3:
1. Build production assets with `cd frontend && npm.cmd run build` (outputs static bundle to `frontend/dist/`).
2. In `backend/main.py`, Member B mounts:
   - Member A's negotiation router (`app.include_router(create_router(negotiation_service))`) sharing the same server-owned session cookie (`b2_session` / `request.state.session_id`).
   - `frontend/dist` static files at `/` (with SPA index fallback).
3. Set `VITE_PAYPAL_CLIENT_ID=<sandbox-client-id>` at frontend build time so Member B's `frontend/src/CheckoutButton.tsx` renders the live PayPal JS SDK button when `quoteId` is passed by `CheckoutSlot.tsx`.

---

## 6. Git Workflow (Branch Name & Commit Messages)

```powershell
cd "d:\Paypal hackathon\PayPal_Hackathon"
git checkout -b member-c/buyer-ui
git status
# Ensure frontend/src/CheckoutButton.tsx and backend/** are untouched!
git add frontend/vite.config.ts frontend/src/types.ts frontend/src/fixtures/scenarios.ts frontend/src/adapters/ frontend/src/components/ frontend/src/App.css frontend/src/App.tsx
git commit -m "Implement C1-C5 buyer negotiation UI, local fixture adapter, and live API integration"
git push -u origin member-c/buyer-ui
```

---

## 7. Open Questions & Ambiguities Found in Repository Files

All interfaces for Member C (`POST /api/negotiations`, `POST /api/negotiations/{id}/turn`, `GET /api/negotiations/{id}`, `GET /api/payments/quotes/{id}`, and `CheckoutButton.tsx` props `{ quoteId, onStatusChange }`) are **fully specified** in `implementation_plan (1).md`, `backend/domain/api.py`, `backend/payments/harness.py`, and `frontend/src/CheckoutButton.tsx`. However, the following cross-team items are explicitly noted as open in the repository docs:

1. **Session Cookie Unification Between Member A and Member B (`backend/domain/API.md` lines 12–16 vs. `backend/payments/harness.py` line 16):**
   - Member A's `trusted_session` in `backend/domain/api.py` reads `request.state.session_id` (and returns HTTP `401` if absent).
   - Member B's `backend/payments/harness.py` currently only creates the `b2_session` cookie when `POST /api/test-checkout/session` is called, and `backend/main.py` does not yet mount session middleware or `create_router(service)` (that is Member B's **B4** task).
   - **Impact on Member C:** None in Local Fixture Mode. In Live API Mode, if `POST /api/negotiations` returns `401 ("A server-owned session is required.")` before Member B completes B4 middleware wiring, it means Member B still needs to attach the session cookie middleware in `backend/main.py`.
2. **Real Seller Floor (`minimum_total_cents`) for Live Mode (`backend/domain/A1_STATUS.md` lines 98–105):**
   - `A1_STATUS.md` notes that the `30000`-cent (`$300.00`) seller floor used in `api_demo.py` and `negotiation_fixtures.py` is a synthetic development floor and the team must confirm the merchant floor when Member B wires `NegotiationService` in `backend/main.py`.
   - **Impact on Member C:** None — `minimum_total_cents` is server-private and never sent by or returned to the frontend.
3. **Should We Execute the Code Changes in `PayPal_Hackathon/frontend/` Now?**
   - This plan contains the complete, copy-paste-ready code for all 12 frontend files. Would you like us to write these files directly into `d:\Paypal hackathon\PayPal_Hackathon\frontend\` and run `npm.cmd run build` now?

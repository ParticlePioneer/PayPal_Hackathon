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

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

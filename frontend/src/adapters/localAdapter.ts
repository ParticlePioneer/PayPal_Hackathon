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

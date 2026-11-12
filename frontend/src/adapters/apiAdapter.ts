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

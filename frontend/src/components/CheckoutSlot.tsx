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
  const [statusCheckedFor, setStatusCheckedFor] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const quote = view?.status === "quoted" ? view.quote : null;
  const quoteId = quote?.id ?? "";

  useEffect(() => {
    if (!quoteId) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [quoteId]);

  const fetchPaymentStatus = useCallback(async () => {
    if (!quoteId) {
      setPaymentRecord(null);
      return;
    }
    setCheckingPayment(true);
    try {
      const result = await adapter.getPaymentStatus(quoteId);
      setPaymentRecord(result);
      setStatusCheckedFor(result ? quoteId : null);
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
    setStatusCheckedFor(null);
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
  const hasFailedOp = Boolean(paymentRecord?.operations.some((o) => o.status === "failed"));
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
    mode === "api" && quote && Date.parse(quote.expires_at) > now &&
    statusCheckedFor === quote.id && !checkingPayment && !hasUncertainOp && !hasFailedOp && !isAlreadyAuthorizedOrCaptured
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

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

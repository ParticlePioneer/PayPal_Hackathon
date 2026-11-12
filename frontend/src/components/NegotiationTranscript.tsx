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

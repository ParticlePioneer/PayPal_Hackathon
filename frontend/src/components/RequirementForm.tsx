import React, { useEffect, useState } from "react";
import { Color, CreateNegotiationRequest, DeliveryMinimum } from "../types";
import {
  APPROVED_DEFAULT_REQUEST,
  formatUsd,
  validateNegotiationRequest,
} from "../fixtures/scenarios";

interface RequirementFormProps {
  initialRequest: CreateNegotiationRequest;
  disabled: boolean;
  canStartNegotiation: boolean;
  hasActiveNegotiation: boolean;
  onStartNegotiation: (payload: CreateNegotiationRequest) => void;
  onLoadPreset: (preset: CreateNegotiationRequest) => void;
}

export default function RequirementForm({
  initialRequest,
  disabled,
  canStartNegotiation,
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
  const [selectedMilestone, setSelectedMilestone] = useState<number>(0);

  useEffect(() => {
    setSku(initialRequest.sku);
    setQuantity(initialRequest.quantity);
    setBudgetDollars((initialRequest.budget_cents / 100).toFixed(2));
    setAllowedColors([...initialRequest.allowed_colors]);
    setPreferredColor(initialRequest.preferred_color);
    setDeadlines(initialRequest.minimum_by_date.map((milestone) => ({ ...milestone })));
    setSelectedMilestone(0);
  }, [initialRequest]);

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
  const scheduledQuantity =
    deadlines.length > 0 ? deadlines[deadlines.length - 1].qty : 0;
  const fulfillmentPercent =
    quantity > 0
      ? Math.min(100, Math.max(0, (scheduledQuantity / quantity) * 100))
      : 0;
  const activeMilestoneIndex = Math.min(
    selectedMilestone,
    Math.max(0, deadlines.length - 1)
  );
  const activeMilestone = deadlines[activeMilestoneIndex];
  const previousMilestoneQty =
    activeMilestoneIndex === 0
      ? 0
      : deadlines[activeMilestoneIndex - 1]?.qty ?? 0;

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
    setDeadlines((prev) => prev.filter((_, idx) => idx !== index));
    setSelectedMilestone((current) =>
      current === index ? Math.max(0, index - 1) : current > index ? current - 1 : current
    );
  }

  function handleMilestoneTabKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number
  ) {
    const tabs =
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]'
      );
    if (!tabs?.length) return;

    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    }

    if (nextIndex !== null) {
      event.preventDefault();
      setSelectedMilestone(nextIndex);
      tabs[nextIndex].focus();
    }
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
    if (!isValid || disabled || !canStartNegotiation) return;
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
            {deadlines.length === 0 && (
              <p className="milestone-empty-state">
                No delivery milestones yet. Add one when you need a delivery
                deadline.
              </p>
            )}
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
                    <button
                      type="button"
                      className="btn-link-danger"
                      disabled={disabled}
                      onClick={() => handleRemoveDeadline(idx)}
                      aria-label={`Remove milestone ${idx + 1}`}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <aside className="order-preview" aria-label="Live order summary">
          <div className="order-preview-header">
            <div>
              <span className="preview-eyebrow">LIVE ORDER SUMMARY</span>
              <h3 className="sub-heading">
                {quantity > 0 ? `${quantity} shirts` : "Order quantity needed"}
                {sku.trim() ? ` · ${sku.trim()}` : ""}
              </h3>
            </div>
            <span
              className={`preview-state ${
                isValid ? "preview-state-ready" : "preview-state-editing"
              }`}
            >
              <span className="preview-state-dot" aria-hidden="true" />
              {isValid
                ? "Ready to negotiate"
                : "Needs attention"}
            </span>
          </div>
          {!isValid && (
            <p className="preview-validation-note" role="status" aria-live="polite">
              <strong>What needs fixing:</strong>{" "}
              {deadlines.length === 0
                ? "Add at least one delivery milestone to continue."
                : validationErrors[0]}
            </p>
          )}

          <div
            className="fulfillment-meter"
            role="progressbar"
            aria-label="Final milestone quantity compared with total order quantity"
            aria-valuemin={0}
            aria-valuemax={Math.max(0, quantity)}
            aria-valuenow={Math.max(0, Math.min(quantity, scheduledQuantity))}
          >
            <span
              className="fulfillment-meter-fill"
              style={{ width: `${fulfillmentPercent}%` }}
            />
          </div>
          <div className="preview-facts">
            <span
              key={`${scheduledQuantity}-${quantity}`}
              className="preview-scheduled-count"
            >
              <strong>
                {Math.max(0, scheduledQuantity)} / {Math.max(0, quantity)}
              </strong>{" "}
              scheduled by final milestone
            </span>
            <span>
              {allowedColors.length > 0
                ? allowedColors.join(" + ")
                : "No colors selected"}
              {preferredColor ? ` · prefers ${preferredColor}` : ""}
            </span>
          </div>

          <div
            className="preview-milestones"
            role="tablist"
            aria-label="Delivery milestones"
          >
            {deadlines.map((milestone, index) => {
              const priorQuantity = index === 0 ? 0 : deadlines[index - 1].qty;
              const batchQuantity = Math.max(0, milestone.qty - priorQuantity);
              return (
                <button
                  type="button"
                  className={`milestone-tab ${
                    activeMilestoneIndex === index ? "active" : ""
                  }`}
                  id={`preview-milestone-tab-${index}`}
                  key={`${index}-${milestone.date}`}
                  role="tab"
                  aria-selected={activeMilestoneIndex === index}
                  aria-controls="preview-milestone-panel"
                  tabIndex={activeMilestoneIndex === index ? 0 : -1}
                  onClick={() => setSelectedMilestone(index)}
                  onKeyDown={(event) => handleMilestoneTabKeyDown(event, index)}
                >
                  <span>{milestone.date || "Choose a date"}</span>
                  <strong>
                    {milestone.qty} total
                    {index > 0 ? ` · +${batchQuantity}` : ""}
                  </strong>
                </button>
              );
            })}
          </div>
          {activeMilestone && (
            <div
              className="milestone-tab-panel"
              id="preview-milestone-panel"
              role="tabpanel"
              aria-labelledby={`preview-milestone-tab-${activeMilestoneIndex}`}
              tabIndex={0}
            >
              <span className="timeline-marker" aria-hidden="true" />
              <span>
                <strong>
                  {Math.max(0, activeMilestone.qty - previousMilestoneQty)} new
                  shirts
                </strong>{" "}
                arrive by {activeMilestone.date || "the selected date"};{" "}
                {activeMilestone.qty} shirts delivered cumulatively.
              </span>
            </div>
          )}
        </aside>

        {/* Strictly Separated Private Budget Box (C2 requirement) */}
        <div className="private-budget-box" role="region" aria-labelledby="private-budget-title">
          <div className="private-budget-header">
            <span className="badge badge-private">
              Private buyer input · server-side only
            </span>
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
            disabled={!isValid || disabled || !canStartNegotiation}
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

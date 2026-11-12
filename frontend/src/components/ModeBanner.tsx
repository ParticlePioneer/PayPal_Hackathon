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

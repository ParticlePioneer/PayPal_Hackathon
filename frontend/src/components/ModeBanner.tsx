import { AdapterMode, FixtureScenarioId } from "../types";
import { FIXTURE_SCENARIOS } from "../fixtures/scenarios";

interface ModeBannerProps {
  mode: AdapterMode;
  theme: "dark" | "light";
  scenarioId: FixtureScenarioId | null;
  busy: boolean;
  showGuide: boolean;
  onModeChange: (mode: AdapterMode) => void;
  onScenarioChange: (scenarioId: FixtureScenarioId) => void;
  onResetSession: () => void;
  onToggleGuide: () => void;
  onToggleTheme: () => void;
}

export default function ModeBanner({
  mode,
  theme,
  scenarioId,
  busy,
  showGuide,
  onModeChange,
  onScenarioChange,
  onResetSession,
  onToggleGuide,
  onToggleTheme,
}: ModeBannerProps) {
  const activeScenario = scenarioId
    ? FIXTURE_SCENARIOS.find((s) => s.id === scenarioId)
    : undefined;

  return (
    <header className="app-header" role="banner">
      <div className="brand-masthead">
        <svg
          className="brand-mark"
          viewBox="10 10 52 52"
          role="img"
          aria-label="AgentNegotiate exchange mark"
        >
          <path
            className="brand-mark-loop"
            d="M17 27a21 21 0 0 1 36-8l4 4"
          />
          <path className="brand-mark-arrow" d="m49 23 8 0-1-8" />
          <path
            className="brand-mark-loop brand-mark-loop-reverse"
            d="M55 45a21 21 0 0 1-36 8l-4-4"
          />
          <path className="brand-mark-arrow" d="m23 49-8 0 1 8" />
          <path
            className="brand-mark-package"
            d="m26 31 10-6 10 6v12l-10 6-10-6z"
          />
          <path className="brand-mark-package-detail" d="m26 31 10 6 10-6M36 37v12" />
        </svg>
        <div className="brand-copy">
          <h1 className="brand-title">AgentNegotiate</h1>
          <p className="brand-subtitle">
            Two agents. One fairer bulk deal.
          </p>
        </div>
      </div>

      <div className="mode-banner">
        <div className="mode-banner-top">
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
              Live API Mode
            </button>
            <button
              type="button"
              className="btn-secondary btn-small"
              onClick={onToggleGuide}
              aria-expanded={showGuide}
            >
              {showGuide ? "Hide Guide" : "Guide"}
            </button>
            <button
              type="button"
              className="btn-secondary btn-small"
              disabled={busy}
              onClick={onResetSession}
            >
              Reset Session
            </button>
            <button
              type="button"
              className="theme-toggle"
              onClick={onToggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              aria-pressed={theme === "dark"}
            >
              {theme === "dark" ? "Dark mode" : "Light mode"}
            </button>
          </div>
        </div>

        {mode === "fixture" ? (
          <div className="mode-notice fixture-notice" role="region" aria-label="Fixture mode configuration">
            <div className="notice-header">
              <span className="badge badge-warning">
                DEVELOPMENT FIXTURE SUBSTITUTE
              </span>
              <span>
                Running against deterministic local fixtures in browser memory.{" "}
                <strong>
                  No live Gemini model calls, database reservations, or real
                  PayPal API calls are made in this mode.
                </strong>
              </span>
            </div>

            <div className="scenario-picker-row">
              <label htmlFor="fixture-scenario-select" className="scenario-label">
                Select H0 Acceptance Scenario:
              </label>
              <div className="scenario-select-wrap">
                <select
                  id="fixture-scenario-select"
                  className="scenario-select"
                  value={scenarioId ?? ""}
                  disabled={busy}
                  onChange={(e) => {
                    if (e.target.value) {
                      onScenarioChange(e.target.value as FixtureScenarioId);
                    }
                  }}
                >
                  <option value="" disabled>
                    Select a predefined scenario
                  </option>
                  {FIXTURE_SCENARIOS.map((s) => (
                    <option
                      key={s.id}
                      value={s.id}
                      className={`scenario-option-${s.id}`}
                    >
                      {s.id === "feasible_split" && "✨ "}
                      {s.id === "friday_shortfall" && "⏰ "}
                      {s.id === "competing_buyer_conflict" && "⚡ "}
                      {s.id === "expired_quote" && "⌛ "}
                      {s.id === "retryable_timeout" && "🔄 "}
                      {s.title} — [{s.badge}]
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {activeScenario ? (
              <p className="scenario-meta-text" key={scenarioId}>
                <strong>Scenario Goal:</strong> {activeScenario.description}{" "}
                <span className="scenario-expected">
                  ({activeScenario.expectedOutcomeText})
                </span>
              </p>
            ) : (
              <p className="scenario-meta-text" key="no-scenario">
                Choose a scenario to load its fixture and start a negotiation.
              </p>
            )}
          </div>
        ) : (
          <div className="mode-notice api-notice" role="region" aria-label="Live API mode notice">
            <span className="badge badge-live">
              LIVE PRODUCTION / SANDBOX ENDPOINTS
            </span>
            <span>
              Connected to <code>POST /api/negotiations</code>,{" "}
              <code>POST /api/negotiations/&#123;id&#125;/turn</code>,{" "}
              <code>GET /api/negotiations/&#123;id&#125;</code>, and{" "}
              <code>/api/payments/*</code> using server-owned session cookies.
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

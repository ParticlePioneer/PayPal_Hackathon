import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import {
  AdapterHttpError,
  AdapterMode,
  CreateNegotiationRequest,
  FixtureScenarioId,
  NegotiationAdapter,
  NegotiationPublicView,
} from "./types";
import {
  APPROVED_DEFAULT_REQUEST,
  FIXTURE_SCENARIOS,
} from "./fixtures/scenarios";
import {
  LocalFixtureAdapter,
  clearLocalFixtureStorage,
} from "./adapters/localAdapter";
import { LiveApiAdapter } from "./adapters/apiAdapter";
import ModeBanner from "./components/ModeBanner";
import RequirementForm from "./components/RequirementForm";
import NegotiationTranscript from "./components/NegotiationTranscript";
import QuotePanel from "./components/QuotePanel";
import CheckoutSlot from "./components/CheckoutSlot";

const ACTIVE_STATE_KEY = "agentnegotiate_active_ui_state_v1";

interface PersistedUiSession {
  mode: AdapterMode;
  scenarioId: FixtureScenarioId;
  negotiationId: string | null;
  lastRequest: CreateNegotiationRequest;
}

function readInitialUiSession(): PersistedUiSession {
  const params = new URLSearchParams(window.location.search);
  const urlMode = params.get("mode");
  const urlScenario = params.get("scenario");
  const urlNegId = params.get("negotiation_id");

  let stored: Partial<PersistedUiSession> = {};
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_STATE_KEY);
    if (raw) stored = JSON.parse(raw) as Partial<PersistedUiSession>;
  } catch {
    // Ignore storage read failure
  }

  const mode: AdapterMode =
    urlMode === "api" || urlMode === "fixture"
      ? urlMode
      : stored.mode === "api" || stored.mode === "fixture"
      ? stored.mode
      : "fixture";

  const validScenarioIds = FIXTURE_SCENARIOS.map((s) => s.id);
  const scenarioId: FixtureScenarioId = validScenarioIds.includes(
    urlScenario as FixtureScenarioId
  )
    ? (urlScenario as FixtureScenarioId)
    : validScenarioIds.includes(stored.scenarioId as FixtureScenarioId)
    ? (stored.scenarioId as FixtureScenarioId)
    : "feasible_split";

  const negotiationId = urlNegId || stored.negotiationId || null;
  const lastRequest = stored.lastRequest ?? APPROVED_DEFAULT_REQUEST;

  return { mode, scenarioId, negotiationId, lastRequest };
}

function syncUrlAndStorage(
  state: PersistedUiSession,
  pushHistory = false
): void {
  try {
    window.sessionStorage.setItem(ACTIVE_STATE_KEY, JSON.stringify(state));
  } catch {
    // Ignore
  }

  const url = new URL(window.location.href);
  url.searchParams.set("mode", state.mode);
  if (state.mode === "fixture") {
    url.searchParams.set("scenario", state.scenarioId);
  } else {
    url.searchParams.delete("scenario");
  }
  if (state.negotiationId) {
    url.searchParams.set("negotiation_id", state.negotiationId);
  } else {
    url.searchParams.delete("negotiation_id");
  }

  if (pushHistory) {
    window.history.pushState(state, "", url.toString());
  } else {
    window.history.replaceState(state, "", url.toString());
  }
}

export default function App() {
  const initial = useMemo(() => readInitialUiSession(), []);
  const [mode, setMode] = useState<AdapterMode>(initial.mode);
  const [scenarioId, setScenarioId] = useState<FixtureScenarioId>(
    initial.scenarioId
  );
  const [activeRequest, setActiveRequest] = useState<CreateNegotiationRequest>(
    initial.lastRequest
  );
  const [view, setView] = useState<NegotiationPublicView | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [autoRunning, setAutoRunning] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState<boolean>(false);

  // Synchronous lock to prevent double-click race conditions (C4 requirement)
  const inFlightRef = useRef<boolean>(false);

  const localAdapter = useMemo(() => new LocalFixtureAdapter(), []);
  const apiAdapter = useMemo(() => new LiveApiAdapter(), []);
  const adapter: NegotiationAdapter =
    mode === "api" ? apiAdapter : localAdapter;

  const restoreNegotiationById = useCallback(
    async (targetAdapter: NegotiationAdapter, negotiationId: string) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setBusy(true);
      setErrorBanner(null);
      try {
        const restored = await targetAdapter.getNegotiation(negotiationId);
        setView(restored);
      } catch (err) {
        if (err instanceof AdapterHttpError && err.status === 404) {
          setView(null);
        } else {
          setErrorBanner(
            err instanceof Error
              ? err.message
              : "Could not restore negotiation state."
          );
        }
      } finally {
        inFlightRef.current = false;
        setBusy(false);
      }
    },
    []
  );

  // Restore existing negotiation on initial mount
  useEffect(() => {
    if (initial.negotiationId) {
      const targetAdapter =
        initial.mode === "api" ? apiAdapter : localAdapter;
      void restoreNegotiationById(targetAdapter, initial.negotiationId);
    }
  }, [initial, apiAdapter, localAdapter, restoreNegotiationById]);

  // Handle Browser Back / Forward buttons (C4 requirement)
  useEffect(() => {
    function handlePopState() {
      const restored = readInitialUiSession();
      setMode(restored.mode);
      setScenarioId(restored.scenarioId);
      setActiveRequest(restored.lastRequest);
      const targetAdapter =
        restored.mode === "api" ? apiAdapter : localAdapter;
      if (restored.negotiationId) {
        void restoreNegotiationById(targetAdapter, restored.negotiationId);
      } else {
        setView(null);
      }
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [apiAdapter, localAdapter, restoreNegotiationById]);

  async function handleStartNegotiation(payload: CreateNegotiationRequest) {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setErrorBanner(null);
    setActiveRequest(payload);

    try {
      const created = await adapter.createNegotiation(payload, scenarioId);
      setView(created);
      syncUrlAndStorage(
        {
          mode,
          scenarioId,
          negotiationId: created.id,
          lastRequest: payload,
        },
        true
      );
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to start negotiation."
      );
    } finally {
      inFlightRef.current = false;
      setBusy(false);
    }
  }

  async function handleAdvanceSingleTurn() {
    if (!view || inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setErrorBanner(null);

    try {
      const next = await adapter.advanceTurn(view.id, view.version);
      setView(next);
    } catch (err) {
      if (err instanceof AdapterHttpError && (err.status === 409 || err.status === 410)) {
        // HTTP 409 (version/stock conflict) or 410 (expired): refresh state via GET
        setErrorBanner(`${err.message} — Refreshed latest state from server.`);
        try {
          const refreshed = await adapter.getNegotiation(view.id);
          setView(refreshed);
        } catch {
          // Ignore secondary error
        }
      } else {
        setErrorBanner(
          err instanceof Error ? err.message : "Failed to advance turn."
        );
      }
    } finally {
      inFlightRef.current = false;
      setBusy(false);
    }
  }

  async function handleAutoRunRemainingTurns() {
    if (!view || inFlightRef.current) return;
    inFlightRef.current = true;
    setBusy(true);
    setAutoRunning(true);
    setErrorBanner(null);

    let currentView = view;
    try {
      for (let i = 0; i < 6; i++) {
        if (
          currentView.status !== "negotiating" &&
          currentView.status !== "retryable_error"
        ) {
          break;
        }
        currentView = await adapter.advanceTurn(
          currentView.id,
          currentView.version
        );
        setView(currentView);
        if (currentView.status === "retryable_error") {
          break;
        }
      }
    } catch (err) {
      if (err instanceof AdapterHttpError && (err.status === 409 || err.status === 410)) {
        setErrorBanner(`${err.message} — Refreshed latest state from server.`);
        try {
          const refreshed = await adapter.getNegotiation(currentView.id);
          setView(refreshed);
        } catch {
          // Ignore
        }
      } else {
        setErrorBanner(
          err instanceof Error ? err.message : "Auto-negotiation interrupted."
        );
      }
    } finally {
      inFlightRef.current = false;
      setBusy(false);
      setAutoRunning(false);
    }
  }

  const handleRefreshNegotiation = useCallback(async () => {
    if (!view || inFlightRef.current) return;
    await restoreNegotiationById(adapter, view.id);
  }, [adapter, view, restoreNegotiationById]);

  function handleModeChange(nextMode: AdapterMode) {
    if (inFlightRef.current) return;
    setMode(nextMode);
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode: nextMode,
        scenarioId,
        negotiationId: null,
        lastRequest: activeRequest,
      },
      true
    );
  }

  function handleScenarioChange(nextScenario: FixtureScenarioId) {
    if (inFlightRef.current) return;
    const meta = FIXTURE_SCENARIOS.find((s) => s.id === nextScenario);
    const nextReq = meta ? meta.presetRequest : APPROVED_DEFAULT_REQUEST;
    setScenarioId(nextScenario);
    setActiveRequest(nextReq);
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode,
        scenarioId: nextScenario,
        negotiationId: null,
        lastRequest: nextReq,
      },
      true
    );
  }

  function handleResetSession() {
    if (inFlightRef.current) return;
    clearLocalFixtureStorage();
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode,
        scenarioId,
        negotiationId: null,
        lastRequest: APPROVED_DEFAULT_REQUEST,
      },
      true
    );
  }

  function handleSimulateForceExpire() {
    if (!view || mode !== "fixture") return;
    setView({
      ...view,
      status: "expired",
      reason: "The quote has expired.",
      quote: null,
    });
  }

  return (
    <div className="app-shell">
      <ModeBanner
        mode={mode}
        scenarioId={scenarioId}
        busy={busy}
        showGuide={showGuide}
        onModeChange={handleModeChange}
        onScenarioChange={handleScenarioChange}
        onResetSession={handleResetSession}
        onToggleGuide={() => setShowGuide((prev) => !prev)}
      />

      {showGuide && (
        <section
          className="card rehearsal-guide-card"
          aria-labelledby="guide-heading"
        >
          <h2 id="guide-heading" className="section-title">
            C5 Screenshot-Free Buyer Screen Sequence & Rehearsal Guide
          </h2>
          <ol className="rehearsal-steps-list">
            <li>
              <strong>Feasible Split ($354.00):</strong> Select{" "}
              <em>1. Feasible Split Deal ($354.00)</em> in Local Fixture Mode
              (or use Live API Mode), click{" "}
              <strong>Start Agent Negotiation</strong>, then click{" "}
              <strong>Complete Negotiation (Auto-Step)</strong>. Observe Turn 1
              (Buyer asks delivery options), Turn 2 (Seller proposes $354 split:
              12 navy by 2026-11-13 + 18 black by 2026-11-16), Turn 3 (Buyer
              accepts). Inspect the Offer Comparison card showing why the $330
              Monday-only option fails Friday while the $354 split qualifies.
              Approve checkout to see the Authorization ID.
            </li>
            <li>
              <strong>Impossible Deadline / 4-Shirt Friday Shortfall:</strong>{" "}
              Switch scenario to{" "}
              <em>2. Impossible Deadline — 4-Shirt Friday Shortfall</em>, click{" "}
              <strong>Start Agent Negotiation</strong> and{" "}
              <strong>Complete Negotiation</strong>. Observe status{" "}
              <code>no_deal</code>, reason{" "}
              <code>At least 4 more shirts are required by 2026-11-13.</code>,{" "}
              <code>quote: null</code>, and disabled checkout button.
            </li>
            <li>
              <strong>Competing Buyers (HTTP 409) & Expiry (HTTP 410):</strong>{" "}
              Switch to scenarios 3, 4, or 5 to verify automatic HTTP 409 conflict
              refresh, UTC quote expiry disabling payment, and retryable turn
              recovery.
            </li>
          </ol>
        </section>
      )}

      {errorBanner && (
        <div className="global-error-banner" role="alert">
          <span>{errorBanner}</span>
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => setErrorBanner(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <main className="workspace-grid">
        <div className="workspace-col">
          <RequirementForm
            initialRequest={activeRequest}
            disabled={busy}
            hasActiveNegotiation={view !== null}
            onStartNegotiation={(payload) => void handleStartNegotiation(payload)}
            onLoadPreset={(preset) => setActiveRequest(preset)}
          />

          <QuotePanel
            view={view}
            onExpireDetected={() => void handleRefreshNegotiation()}
          />
        </div>

        <div className="workspace-col">
          <NegotiationTranscript
            view={view}
            activeRequest={activeRequest}
            busy={busy}
            autoRunning={autoRunning}
            onAdvanceTurn={() => void handleAdvanceSingleTurn()}
            onAutoRunTurns={() => void handleAutoRunRemainingTurns()}
            onRefresh={() => void handleRefreshNegotiation()}
          />

          <CheckoutSlot
            mode={mode}
            adapter={adapter}
            view={view}
            onRefreshNegotiation={() => void handleRefreshNegotiation()}
            onSimulateForceExpire={
              mode === "fixture" ? handleSimulateForceExpire : undefined
            }
          />
        </div>
      </main>
    </div>
  );
}

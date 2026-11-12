import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
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
  DEFAULT_ORDER_REQUEST,
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
const THEME_STORAGE_KEY = "agentnegotiate_theme";

type Theme = "dark" | "light";
type WorkspacePanel = "order" | "negotiation" | "quote" | "checkout";

const WORKSPACE_PANELS: {
  id: WorkspacePanel;
  label: string;
  description: string;
}[] = [
  { id: "order", label: "Order", description: "Set quantity and delivery needs" },
  { id: "negotiation", label: "Negotiation", description: "Follow both agents" },
  { id: "quote", label: "Quote", description: "Review reserved inventory" },
  { id: "checkout", label: "Checkout", description: "Authorize with PayPal" },
];

function readInitialTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "light"
      ? "light"
      : "dark";
  } catch {
    return "dark";
  }
}

interface PersistedUiSession {
  mode: AdapterMode;
  scenarioId: FixtureScenarioId | null;
  scenarioSelectionExplicit?: boolean;
  negotiationId: string | null;
  lastRequest: CreateNegotiationRequest;
}

function readInitialUiSession(): PersistedUiSession {
  const params = new URLSearchParams(window.location.search);
  const urlMode = params.get("mode");
  const urlScenario = params.get("scenario");
  const urlNegId = params.get("negotiation_id");

  let stored: Partial<PersistedUiSession> = {};
  let hasStoredSession = false;
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_STATE_KEY);
    if (raw) {
      stored = JSON.parse(raw) as Partial<PersistedUiSession>;
      hasStoredSession = true;
    }
  } catch {
    // Ignore storage read failure
  }

  const mode: AdapterMode =
    urlMode === "api" || urlMode === "fixture"
      ? urlMode
      : stored.mode === "api" || stored.mode === "fixture"
      ? stored.mode
      : import.meta.env.VITE_DEFAULT_MODE === "api" ? "api" : "fixture";

  const validScenarioIds = FIXTURE_SCENARIOS.map((s) => s.id);
  const negotiationId = urlNegId || stored.negotiationId || null;
  const legacyImplicitScenario =
    hasStoredSession &&
    stored.scenarioSelectionExplicit !== true &&
    !negotiationId;
  const scenarioId: FixtureScenarioId | null = legacyImplicitScenario
    ? null
    : validScenarioIds.includes(urlScenario as FixtureScenarioId)
    ? (urlScenario as FixtureScenarioId)
    : validScenarioIds.includes(stored.scenarioId as FixtureScenarioId)
    ? (stored.scenarioId as FixtureScenarioId)
    : null;
  const lastRequest = stored.lastRequest ?? DEFAULT_ORDER_REQUEST;

  return { mode, scenarioId, negotiationId, lastRequest };
}

function syncUrlAndStorage(
  state: PersistedUiSession,
  pushHistory = false
): void {
  const persistedState = {
    ...state,
    scenarioSelectionExplicit: state.scenarioId !== null,
  };
  try {
    window.sessionStorage.setItem(ACTIVE_STATE_KEY, JSON.stringify(persistedState));
  } catch {
    // Ignore
  }

  const url = new URL(window.location.href);
  url.searchParams.set("mode", state.mode);
  if (state.mode === "fixture" && state.scenarioId) {
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
    window.history.pushState(persistedState, "", url.toString());
  } else {
    window.history.replaceState(persistedState, "", url.toString());
  }
}

export default function App() {
  const initial = useMemo(() => readInitialUiSession(), []);
  const [mode, setMode] = useState<AdapterMode>(initial.mode);
  const [scenarioId, setScenarioId] = useState<FixtureScenarioId | null>(
    initial.scenarioId
  );
  const [activeRequest, setActiveRequest] = useState<CreateNegotiationRequest>(
    initial.lastRequest
  );
  const [view, setView] = useState<NegotiationPublicView | null>(null);
  const [formResetKey, setFormResetKey] = useState<number>(0);
  const [busy, setBusy] = useState<boolean>(false);
  const [autoRunning, setAutoRunning] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState<boolean>(false);
  const [theme, setTheme] = useState<Theme>(readInitialTheme);
  const [activePanel, setActivePanel] = useState<WorkspacePanel>("order");
  const previousPanelRef = useRef<WorkspacePanel>("order");

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Theme selection still applies for the current page when storage is unavailable.
    }
  }, [theme]);

  useEffect(() => {
    if (previousPanelRef.current === activePanel) return;
    previousPanelRef.current = activePanel;

    document
      .querySelector<HTMLElement>(
        `#workspace-panel-${activePanel} > .card`
      )
      ?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start",
      });
  }, [activePanel]);

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
        setActivePanel(
          restored.status === "quoted" ||
            restored.status === "no_deal" ||
            restored.status === "expired"
            ? "quote"
            : "negotiation"
        );
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
        setActivePanel("order");
      }
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [apiAdapter, localAdapter, restoreNegotiationById]);

  async function handleStartNegotiation(payload: CreateNegotiationRequest) {
    if (inFlightRef.current) return;
    if (mode === "fixture" && !scenarioId) {
      setErrorBanner("Select a predefined fixture scenario before starting.");
      return;
    }
    inFlightRef.current = true;
    setBusy(true);
    setErrorBanner(null);
    setActiveRequest(payload);

    try {
      const created = await adapter.createNegotiation(
        payload,
        scenarioId ?? "feasible_split"
      );
      setView(created);
      setActivePanel("negotiation");
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
      if (next.status === "quoted" || next.status === "no_deal" || next.status === "expired") {
        setActivePanel("quote");
      }
    } catch (err) {
      if (err instanceof AdapterHttpError && (err.status === 409 || err.status === 410)) {
        // HTTP 409 (version/stock conflict) or 410 (expired): refresh state via GET
        setErrorBanner(`${err.message} — Refreshed latest state from server.`);
        try {
          const refreshed = await adapter.getNegotiation(view.id);
          setView(refreshed);
          if (
            refreshed.status === "quoted" ||
            refreshed.status === "no_deal" ||
            refreshed.status === "expired"
          ) {
            setActivePanel("quote");
          }
        } catch (refreshError) {
          setErrorBanner(
            `${err.message} The latest negotiation state could not be refreshed: ${
              refreshError instanceof Error
                ? refreshError.message
                : "Unknown refresh error."
            }`
          );
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
        if (
          currentView.status === "quoted" ||
          currentView.status === "no_deal" ||
          currentView.status === "expired"
        ) {
          setActivePanel("quote");
        }
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
          if (
            refreshed.status === "quoted" ||
            refreshed.status === "no_deal" ||
            refreshed.status === "expired"
          ) {
            setActivePanel("quote");
          }
        } catch (refreshError) {
          setErrorBanner(
            `${err.message} The latest negotiation state could not be refreshed: ${
              refreshError instanceof Error
                ? refreshError.message
                : "Unknown refresh error."
            }`
          );
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
    setActivePanel("order");
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

  function handleScenarioChange(
    nextScenario: FixtureScenarioId,
    nextMode: AdapterMode = mode
  ) {
    if (inFlightRef.current) return;
    const meta = FIXTURE_SCENARIOS.find((s) => s.id === nextScenario);
    const nextReq = meta ? meta.presetRequest : APPROVED_DEFAULT_REQUEST;
    setMode(nextMode);
    setScenarioId(nextScenario);
    setActiveRequest(nextReq);
    setActivePanel("order");
    setView(null);
    setErrorBanner(null);
    syncUrlAndStorage(
      {
        mode: nextMode,
        scenarioId: nextScenario,
        negotiationId: null,
        lastRequest: nextReq,
      },
      true
    );
  }

  function handleGuideScenario(nextScenario: FixtureScenarioId) {
    if (inFlightRef.current) return;
    handleScenarioChange(nextScenario, "fixture");
    setShowGuide(false);
    window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>("#workspace-panel-order > .card")
        ?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
          block: "start",
        });
    });
  }

  function handleResetSession() {
    if (inFlightRef.current) return;
    clearLocalFixtureStorage();
    const resetScenario: FixtureScenarioId | null = null;
    setScenarioId(resetScenario);
    setActiveRequest(DEFAULT_ORDER_REQUEST);
    setView(null);
    setErrorBanner(null);
    setFormResetKey((currentKey) => currentKey + 1);
    setActivePanel("order");
    syncUrlAndStorage(
      {
        mode,
        scenarioId: resetScenario,
        negotiationId: null,
        lastRequest: DEFAULT_ORDER_REQUEST,
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

  function getPanelStatus(panel: WorkspacePanel): string {
    if (panel === "order") {
      return view ? "Request saved" : "Needs setup";
    }
    if (panel === "negotiation") {
      if (!view) return "Waiting for order";
      if (view.status === "negotiating") return `Turn ${view.version} of 6`;
      if (view.status === "retryable_error") return "Retry available";
      return view.status.replace("_", " ");
    }
    if (panel === "quote") {
      if (view?.status === "quoted" && view.quote) return "Stock reserved";
      if (view?.status === "no_deal") return "No quote";
      if (view?.status === "expired") return "Expired";
      return "Not ready";
    }
    if (view?.status === "quoted" && view.quote) return "Approval available";
    return "Unavailable";
  }

  function handlePanelKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number
  ) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      nextIndex = (index + 1) % WORKSPACE_PANELS.length;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      nextIndex = (index - 1 + WORKSPACE_PANELS.length) % WORKSPACE_PANELS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = WORKSPACE_PANELS.length - 1;
    }
    if (nextIndex === null) return;

    event.preventDefault();
    setActivePanel(WORKSPACE_PANELS[nextIndex].id);
    const tabs =
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]'
      );
    tabs?.[nextIndex]?.focus();
  }

  return (
    <div className="app-shell">
      <ModeBanner
        mode={mode}
        scenarioId={scenarioId}
        busy={busy}
        showGuide={showGuide}
        theme={theme}
        onModeChange={handleModeChange}
        onScenarioChange={handleScenarioChange}
        onResetSession={handleResetSession}
        onToggleGuide={() => setShowGuide((prev) => !prev)}
        onToggleTheme={() =>
          setTheme((currentTheme) => (currentTheme === "dark" ? "light" : "dark"))
        }
      />

      {showGuide && (
        <section
          className="card rehearsal-guide-card"
          aria-labelledby="guide-heading"
        >
          <div className="guide-heading">
            <div>
              <span className="guide-kicker">QUICK TOUR</span>
              <h2 id="guide-heading">See the negotiation in action</h2>
            </div>
            <p>Pick a scenario to load it and jump straight into the order form.</p>
          </div>
          <ol className="rehearsal-steps-list">
            <li className="guide-step guide-step-success">
              <span className="guide-step-number" aria-hidden="true">01</span>
              <div className="guide-step-content">
                <span className="guide-step-label">Best-case deal</span>
                <h3>Split delivery · $354</h3>
                <p>
                  Choose <strong>Feasible Split Deal</strong>, start the
                  negotiation, then complete the turns. See 12 navy shirts
                  arrive Friday and 18 black shirts Monday. Compare it with the
                  $330 Monday-only offer, then authorize checkout.
                </p>
                <button
                  type="button"
                  className="guide-run-button"
                  disabled={busy}
                  onClick={() => handleGuideScenario("feasible_split")}
                >
                  Load scenario
                </button>
              </div>
            </li>
            <li className="guide-step guide-step-warning">
              <span className="guide-step-number" aria-hidden="true">02</span>
              <div className="guide-step-content">
                <span className="guide-step-label">Deadline challenge</span>
                <h3>Four shirts short by Friday</h3>
                <p>
                  Choose <strong>4-Shirt Friday Shortfall</strong> and complete
                  the negotiation. The result explains the shortfall, returns
                  no quote, and keeps checkout unavailable.
                </p>
                <button
                  type="button"
                  className="guide-run-button"
                  disabled={busy}
                  onClick={() => handleGuideScenario("friday_shortfall")}
                >
                  Load scenario
                </button>
              </div>
            </li>
            <li className="guide-step guide-step-live">
              <span className="guide-step-number" aria-hidden="true">03</span>
              <div className="guide-step-content">
                <span className="guide-step-label">Edge cases</span>
                <h3>Conflict, expiry, and retry</h3>
                <p>
                  Try scenarios 3–5 to see a stock conflict refresh, an expired
                  reservation blocking payment, and a timed-out turn resume.
                </p>
                <button
                  type="button"
                  className="guide-run-button"
                  disabled={busy}
                  onClick={() =>
                    handleGuideScenario("competing_buyer_conflict")
                  }
                >
                  Load stock conflict
                </button>
              </div>
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

      <main className="workspace-layout">
        <nav className="workspace-sidebar" aria-label="Negotiation workspace">
          <div className="sidebar-heading">
            <span className="sidebar-eyebrow">WORKSPACE</span>
            <h2>Order flow</h2>
            <p>Move through each step at your own pace.</p>
          </div>
          <div className="sidebar-tabs" role="tablist" aria-orientation="vertical">
            {WORKSPACE_PANELS.map((panel, index) => {
              const isActive = activePanel === panel.id;
              const status = getPanelStatus(panel.id);
              return (
                <button
                  type="button"
                  key={panel.id}
                  id={`workspace-tab-${panel.id}`}
                  className={`sidebar-tab ${isActive ? "active" : ""}`}
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`workspace-panel-${panel.id}`}
                  aria-current={isActive ? "step" : undefined}
                  tabIndex={isActive ? 0 : -1}
                  onClick={() => setActivePanel(panel.id)}
                  onKeyDown={(event) => handlePanelKeyDown(event, index)}
                >
                  <span className="sidebar-step" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="sidebar-tab-copy">
                    <strong>{panel.label}</strong>
                    <span>{panel.description}</span>
                  </span>
                  <span className="sidebar-status">{status}</span>
                </button>
              );
            })}
          </div>
          <div className="sidebar-mode-note">
            <span className={`mode-indicator mode-${mode}`} />
            {mode === "fixture" ? "Local fixture mode" : "Live API mode"}
          </div>
        </nav>

        <div className="workspace-stage">
          <section
            className="workspace-panel"
            id="workspace-panel-order"
            role="tabpanel"
            aria-labelledby="workspace-tab-order"
            hidden={activePanel !== "order"}
            tabIndex={0}
          >
            <RequirementForm
              key={formResetKey}
              initialRequest={activeRequest}
              disabled={busy}
              canStartNegotiation={mode !== "fixture" || scenarioId !== null}
              hasActiveNegotiation={view !== null}
              onStartNegotiation={(payload) => void handleStartNegotiation(payload)}
              onLoadPreset={(preset) => setActiveRequest(preset)}
            />
          </section>

          <section
            className="workspace-panel"
            id="workspace-panel-negotiation"
            role="tabpanel"
            aria-labelledby="workspace-tab-negotiation"
            hidden={activePanel !== "negotiation"}
            tabIndex={0}
          >
            <NegotiationTranscript
              view={view}
              activeRequest={activeRequest}
              busy={busy}
              autoRunning={autoRunning}
              onAdvanceTurn={() => void handleAdvanceSingleTurn()}
              onAutoRunTurns={() => void handleAutoRunRemainingTurns()}
              onRefresh={() => void handleRefreshNegotiation()}
            />
          </section>

          <section
            className="workspace-panel"
            id="workspace-panel-quote"
            role="tabpanel"
            aria-labelledby="workspace-tab-quote"
            hidden={activePanel !== "quote"}
            tabIndex={0}
          >
            <QuotePanel
              view={view}
              onExpireDetected={() => void handleRefreshNegotiation()}
            />
          </section>

          <section
            className="workspace-panel"
            id="workspace-panel-checkout"
            role="tabpanel"
            aria-labelledby="workspace-tab-checkout"
            hidden={activePanel !== "checkout"}
            tabIndex={0}
          >
            <CheckoutSlot
              mode={mode}
              adapter={adapter}
              view={view}
              onRefreshNegotiation={() => void handleRefreshNegotiation()}
              onSimulateForceExpire={
                mode === "fixture" ? handleSimulateForceExpire : undefined
              }
            />
          </section>
        </div>
      </main>
    </div>
  );
}

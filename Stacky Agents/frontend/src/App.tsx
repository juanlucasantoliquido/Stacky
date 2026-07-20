import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import UnblockerPage from "./pages/UnblockerPage";
import SystemLogsPage from "./pages/SystemLogsPage";
import PMCommandCenter from "./pages/PMCommandCenter";
import SettingsPage from "./pages/SettingsPage";
import DocsPage from "./pages/DocsPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import MemoryPage from "./pages/MemoryPage";
import ExecutionHistoryPage from "./pages/ExecutionHistoryPage";
import ReviewInboxPage from "./pages/ReviewInboxPage";
import MigratorPage from "./pages/MigratorPage"; // Plan 74
import { DevOpsPage } from "./pages/DevOpsPage"; // Plan 87
import { DbComparePage } from "./components/dbcompare/DbComparePage"; // Plan 122
import CostCenterPage from "./pages/CostCenterPage"; // Plan 142
import PlansBoardPage from "./pages/PlansBoardPage"; // Plan 128
import EvolutionCenterPage from "./pages/EvolutionCenterPage"; // Plan 167
import TopBar from "./components/TopBar";
import HealthBanner from "./components/HealthBanner";
import ConnectionBanner from "./components/ConnectionBanner";
import CommandPalette from "./components/CommandPalette";
import DailyStandupModal from "./components/DailyStandupModal";
import OnboardingTour from "./components/OnboardingTour";
import UndoToastHost from "./components/UndoToastHost";
import ShortcutsCheatsheet from "./components/ShortcutsCheatsheet";
import DemoModeBanner from "./components/DemoModeBanner";
import CodexConsoleDock from "./components/CodexConsoleDock";
import ActiveRunsPanel from "./components/ActiveRunsPanel";
import PageErrorBoundary from "./components/PageErrorBoundary";
import { probeFlagHealth, nextEnabledState } from "./utils/flagHealth";
import { toggleNavTab } from "./services/uiGuards";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { safeStorage, migrateLegacy, shouldAutoShow } from "./services/onboarding";
import { useOnboardingStore } from "./store/onboardingStore";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import { useGlobalExecutionNotifier } from "./hooks/useGlobalExecutionNotifier";
import { useRunActivityCapture } from "./hooks/useRunActivityCapture"; // Plan 152
import { HarnessFlags } from "./api/endpoints"; // Plan 152 — lectura del flag del centro de actividad
import { useReviewInboxCount } from "./hooks/useReviewInboxCount";
import { reviewBadgeLabel } from "./services/reviewInbox";
import AppSidebar from "./components/shell/AppSidebar";
import {
  computeVisibleTabs, parseCollapsed, SIDEBAR_COLLAPSED_KEY,
} from "./components/shell/shellNav";
// Plan 165 F3 — fuente única del contrato de rutas (type Tab/TAB_PATHS/parseo).
import { parseRoute, serializeRoute, TAB_PATHS, type Tab, type RouteState } from "./services/routes";
import styles from "./App.module.css";

export default function App() {
  // Plan 165 F3 (C1) — la ruta es ESTADO (no un ref congelado): popstate y la
  // navegación in-app la actualizan, y las páginas reciben props VIVAS (exec/subTab).
  const [route, setRoute] = useState<RouteState>(() =>
    parseRoute(window.location.pathname, window.location.search),
  );
  const tab = route.tab;  // todo el JSX existente que lee `tab` sigue idéntico
  // Plan 136 F7 — espejo del tab para handlers registrados con deps [] (el
  // closure del keydown quedaba congelado en el valor de montaje).
  const tabRef = useRef(tab);
  useEffect(() => { tabRef.current = tab; }, [tab]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);
  const sections = useUiSectionsStore((s) => s.sections);
  // Plan 74: tab migrador visible solo si el flag está ON en el backend
  const [migradorEnabled, setMigradorEnabled] = useState(false);
  // Plan 87: tab DevOps visible solo si el flag está ON en el backend
  const [devopsEnabled, setDevopsEnabled] = useState(false);
  // Plan 122: tab Comparador BD visible solo si el flag está ON en el backend
  const [dbCompareEnabled, setDbCompareEnabled] = useState(false);
  // Plan 142: tab Centro de Costos visible solo si el flag está ON en el backend
  // (default ON, C1 — pero se prueba en vivo igual que migrador/devops/dbcompare).
  const [costCenterEnabled, setCostCenterEnabled] = useState(false);
  // Plan 139: App Shell v2 (sidebar agrupada) — flag leída una sola vez al montar.
  const [shellV2Enabled, setShellV2Enabled] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
    () => parseCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)),
  );
  const toggleSidebar = () => {
    setSidebarCollapsed((c) => {
      const next = !c;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "true" : "false");
      return next;
    });
  };
  // Plan 128: tab Planes visible solo si el flag está ON en el backend
  const [planesEnabled, setPlanesEnabled] = useState(false);
  // Plan 167: tab Evolución visible solo si el flag está ON en el backend
  const [evolutionEnabled, setEvolutionEnabled] = useState(false);
  // Plan 129: búsqueda profunda de la paleta (Ctrl+K) solo si el flag está ON en el backend
  const [deepSearchEnabled, setDeepSearchEnabled] = useState(false);

  // Plan 152 — Centro de Actividad: flag default ON (fail-open). Se lee del
  // registro canónico de flags vía el endpoint existente; OFF ⇒ campana oculta
  // + captura apagada (C2). No usa probeFlagHealth (135): ese es para health.
  const [notifEnabled, setNotifEnabled] = useState(true);

  useGlobalExecutionNotifier();
  useRunActivityCapture(notifEnabled); // Plan 152 F2 — reusa la query compartida (0 requests nuevos)
  const reviewCount = useReviewInboxCount();
  const reviewBadge = reviewBadgeLabel(reviewCount);

  // Plan 165 F3 [A1] — navigateToRoute: LA API de navegación tipada del router
  // casero. selectTab/navigateTo la reusan por dentro; es el punto de consumo del
  // plan 152. El pushState queda FUERA de todo updater de setState (regla §3.4
  // StrictMode: los updaters se invocan dos veces en dev → duplicarían historial).
  const navigateToRoute = (next: RouteState) => {
    const url = serializeRoute(next);
    const current = window.location.pathname + window.location.search;
    if (url !== current) window.history.pushState({}, "", url);
    setRoute(next);
  };

  // selectTab con query:{} LIMPIA el querystring al cambiar de tab (idéntico al
  // pushState(TAB_PATHS[next]) anterior); los filtros persisten en localStorage (F2).
  const selectTab = (next: Tab) => navigateToRoute({ tab: next, query: {} });

  const navigateTo = (path: string) => {           // la paleta sigue pasando strings
    const [pathname, search = ""] = path.split("?");
    navigateToRoute(parseRoute(pathname, search ? `?${search}` : ""));
  };

  useEffect(() => {
    initPreferences();
    initUiSections();
    // Plan 135 F6: solo un JSON válido con flag_enabled===true|false es
    // veredicto. Fallo de red/parseo => retry (≤2, backoff) y, si persiste,
    // "unknown" que CONSERVA el estado previo (nextEnabledState) en vez de
    // ocultar el tab toda la sesión. La desactivación real de la flag
    // (JSON ok con flag_enabled=false) sigue ocultando el tab, igual que hoy.
    let alive = true;
    void probeFlagHealth("/api/migrator/health").then((v) => {
      if (alive) setMigradorEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/devops/health").then((v) => {
      if (alive) setDevopsEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/db-compare/health").then((v) => {
      if (alive) setDbCompareEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/metrics/cost-center/health").then((v) => {
      if (alive) setCostCenterEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/plans-board/health").then((v) => {
      if (alive) setPlanesEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/evolution/health").then((v) => {
      if (alive) setEvolutionEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/search/health").then((v) => {
      if (alive) setDeepSearchEnabled((prev) => nextEnabledState(prev, v));
    });
    // Plan 139: lee la flag del shell v2 una sola vez al montar (recargar la
    // página para ver el efecto de un toggle; no hay re-montaje en caliente).
    fetch("/api/diag/health")
      .then((r) => r.json())
      .then((d: { shell_v2_enabled?: boolean }) => {
        if (alive) setShellV2Enabled(d.shell_v2_enabled === true);
      })
      .catch(() => {
        if (alive) setShellV2Enabled(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Plan 165 F3 (C1) — popstate re-deriva TODO el estado (tab+subtab+exec), no
  // solo el tab: Atrás/Adelante mueven sub-tab y drawer con la página ya montada.
  useEffect(() => {
    const onPopState = () =>
      setRoute(parseRoute(window.location.pathname, window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Plan 165 F3 (C5) — normalización backward-compat al montar: parseRoute ya
  // llevó /?exec= a {tab:"history"}; acá reescribimos la barra a la forma canónica.
  // replaceState (no pushState): no duplica historial ni dispara el double-push.
  useEffect(() => {
    const canonical = serializeRoute(route);
    const current = window.location.pathname + window.location.search;
    if (canonical !== current) window.history.replaceState({}, "", canonical);
  }, []);  // SOLO al montar

  // Plan 152 F3 — valor efectivo del flag del Centro de Actividad. FAIL-OPEN:
  // default ON aunque el flag no esté en la respuesta o falle la red (UI aditiva).
  useEffect(() => {
    let alive = true;
    HarnessFlags.list()
      .then((r) => {
        if (!alive) return;
        const f = r.flags.find((x) => x.key === "STACKY_NOTIFICATION_CENTER_ENABLED");
        setNotifEnabled(f ? f.value === true : true);
      })
      .catch(() => {
        if (alive) setNotifEnabled(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Plan 151 F5 — migrar la key vieja del prototipo y auto-mostrar el tour SOLO
  // en first-run real. Este effect NO llama resetSeen (C2: nada en producción
  // la llama). Al cerrar el tour, closeTour() marca `seen` y no vuelve a
  // auto-aparecer.
  useEffect(() => {
    const s = safeStorage();
    migrateLegacy(s);
    if (shouldAutoShow(s)) {
      useOnboardingStore.getState().setOpen(true);
    }
  }, []);

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const target = ev.target as HTMLElement | null;
      const editable =
        target &&
        (["INPUT", "TEXTAREA"].includes(target.tagName) || target.isContentEditable);
      const isPaletteShortcut =
        (ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k";
      const isCheatsheet = !editable && ev.key === "?" && !ev.ctrlKey && !ev.metaKey;
      const isToggleNav = (ev.ctrlKey || ev.metaKey) && ev.key === "/";
      if (isPaletteShortcut) {
        ev.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (isCheatsheet) {
        ev.preventDefault();
        setCheatsheetOpen((v) => !v);
      } else if (isToggleNav) {
        ev.preventDefault();
        // Plan 136 F7 — usar el tab ACTUAL (tabRef) y reusar selectTab, que ya
        // hace pushState con guard de pathname. PROHIBIDO meter pushState dentro
        // del updater de setTab: la app monta en <React.StrictMode> (main.tsx:13)
        // y en dev los updaters se invocan DOS veces (duplicaría el historial).
        selectTab(toggleNavTab(tabRef.current));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Si el usuario tenía seleccionado un tab opcional que acaba de ocultarse,
  // fallback a "tickets" (la vista índice) para no quedar en blanco. Incluye
  // "team" (Mi Equipo), que ahora es ocultable y default oculto: si el deep-link
  // "/team" apunta a un equipo oculto, rebota a tickets.
  useEffect(() => {
    if (tab === "team" && !sections.team) selectTab("tickets");
    else if (tab === "pm" && !sections.pm) selectTab("tickets");
    else if (tab === "logs" && !sections.logs) selectTab("tickets");
    else if (tab === "docs" && !sections.docs) selectTab("tickets");
    else if (tab === "memory" && !sections.memory) selectTab("tickets");
    else if (tab === "migrador" && !migradorEnabled) selectTab("tickets");
    else if (tab === "devops" && !devopsEnabled) selectTab("tickets");
    else if (tab === "dbcompare" && !dbCompareEnabled) selectTab("tickets");
    else if (tab === "costcenter" && !costCenterEnabled) selectTab("tickets");
    else if (tab === "planes" && !planesEnabled) selectTab("tickets");
    else if (tab === "evolution" && !evolutionEnabled) selectTab("tickets");
  }, [tab, sections.team, sections.pm, sections.logs, sections.docs, sections.memory, migradorEnabled, devopsEnabled, dbCompareEnabled, costCenterEnabled, planesEnabled, evolutionEnabled]);

  const visibleTabs = computeVisibleTabs({
    sections: {
      team: !!sections.team, pm: !!sections.pm, logs: !!sections.logs,
      docs: !!sections.docs, memory: !!sections.memory,
    },
    migradorEnabled, devopsEnabled, dbCompareEnabled, costCenterEnabled, planesEnabled,
    evolutionEnabled,
  });

  // [Contrato §3.2 Plan 139 — Plan 134] Espejo del badge de la nav v1: MISMA
  // fuente (reviewBadge = reviewBadgeLabel(reviewCount)); AppSidebar decide su
  // propia presentación (itemBadge) — no se reusa el markup navBadge de v1.
  const shellBadges: Partial<Record<Tab, ReactNode>> = {
    review: reviewBadge,
  };

  // Plan 139 §3.7 — extraído verbatim de las 14 líneas de montaje (mismos
  // condicionales exactos); un fragment de React es transparente en el DOM,
  // así que se renderiza IGUAL en ambas ramas (v1 nav / v2 sidebar): cero
  // remount extra, mismo timing de montaje/desmontaje.
  const pages = (
    <>
      {tab === "team"     && sections.team && <TeamScreen />}
      {tab === "tickets"  && <TicketBoard />}
      {tab === "review"   && <ReviewInboxPage />}
      {tab === "unblocker" && <UnblockerPage />}
      {tab === "pm"       && sections.pm   && <PMCommandCenter />}
      {tab === "logs"     && sections.logs && <SystemLogsPage />}
      {tab === "settings" && <SettingsPage subTab={route.subtab ?? null} />}
      {tab === "docs"     && sections.docs && <DocsPage />}
      {tab === "memory"   && sections.memory && <MemoryPage />}
      {tab === "diagnostics" && <DiagnosticsPage />}
      {tab === "history"     && <ExecutionHistoryPage exec={route.exec ?? null} />}
      {tab === "migrador"    && migradorEnabled && <MigratorPage />} {/* Plan 74 */}
      {tab === "devops"      && devopsEnabled && <DevOpsPage />} {/* Plan 87 */}
      {tab === "dbcompare"   && dbCompareEnabled && <DbComparePage />} {/* Plan 122 */}
      {tab === "costcenter"  && costCenterEnabled && <CostCenterPage />} {/* Plan 142 */}
      {tab === "planes"      && planesEnabled && <PlansBoardPage />} {/* Plan 128 */}
      {tab === "evolution"   && evolutionEnabled && <EvolutionCenterPage />} {/* Plan 167 */}
    </>
  );

  return (
    <div className={styles.appRoot}>
      <DemoModeBanner />
      <TopBar
        onGoToTeam={sections.team ? () => selectTab("team") : undefined}
        shellV2={shellV2Enabled}
        notificationsEnabled={notifEnabled}
        onActivityNavigate={(nav) => selectTab(nav.tab as Tab)}
      />
      <ConnectionBanner />
      <HealthBanner />

      {shellV2Enabled ? (
        <div className={styles.shellLayout}>
          <AppSidebar
            activeTab={tab}
            onSelect={selectTab}
            visibleTabs={visibleTabs}
            collapsed={sidebarCollapsed}
            onToggleCollapsed={toggleSidebar}
            badges={shellBadges}
          />
          <main className={styles.shellContent}>
            <PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>
          </main>
        </div>
      ) : (
        <>
          {/* Tabs de navegación principal */}
          <nav className={styles.nav} data-tour="nav">
            {sections.team && (
              <button
                className={`${styles.navTab} ${tab === "team" ? styles.active : ""}`}
                onClick={() => selectTab("team")}
              >
                ⚡ Mi Equipo
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "tickets" ? styles.active : ""}`}
              onClick={() => selectTab("tickets")}
            >
              📋 Tickets ADO
            </button>
            <button
              className={`${styles.navTab} ${tab === "review" ? styles.active : ""}`}
              onClick={() => selectTab("review")}
            >
              🧭 Revisión
              {reviewBadge != null && (
                <span
                  className={styles.navBadge}
                  aria-label={`${reviewCount} ejecuciones esperando revisión`}
                >
                  {reviewBadge}
                </span>
              )}
            </button>
            <button
              className={`${styles.navTab} ${tab === "unblocker" ? styles.active : ""}`}
              onClick={() => selectTab("unblocker")}
            >
              🧹 Desatascador
            </button>
            {sections.pm && (
              <button
                className={`${styles.navTab} ${tab === "pm" ? styles.active : ""}`}
                onClick={() => selectTab("pm")}
              >
                📊 PM
              </button>
            )}
            {sections.logs && (
              <button
                className={`${styles.navTab} ${tab === "logs" ? styles.active : ""}`}
                onClick={() => selectTab("logs")}
              >
                🔍 System Logs
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "settings" ? styles.active : ""}`}
              onClick={() => selectTab("settings")}
            >
              ⚙️ Configuración
            </button>
            {sections.docs && (
              <button
                className={`${styles.navTab} ${tab === "docs" ? styles.active : ""}`}
                onClick={() => selectTab("docs")}
              >
                📄 Docs
              </button>
            )}
            {sections.memory && (
              <button
                className={`${styles.navTab} ${tab === "memory" ? styles.active : ""}`}
                onClick={() => selectTab("memory")}
              >
                Memoria
              </button>
            )}
            <button
              className={`${styles.navTab} ${tab === "diagnostics" ? styles.active : ""}`}
              onClick={() => selectTab("diagnostics")}
            >
              🩺 Diagnóstico
            </button>
            <button
              className={`${styles.navTab} ${tab === "history" ? styles.active : ""}`}
              onClick={() => selectTab("history")}
            >
              📋 Historial
            </button>
            {migradorEnabled && (
              <button
                className={`${styles.navTab} ${tab === "migrador" ? styles.active : ""}`}
                onClick={() => selectTab("migrador")}
              >
                Migrador
              </button>
            )}
            {devopsEnabled && (
              <button
                className={`${styles.navTab} ${tab === "devops" ? styles.active : ""}`}
                onClick={() => selectTab("devops")}
              >
                DevOps
              </button>
            )}
            {dbCompareEnabled && (
              <button
                className={`${styles.navTab} ${tab === "dbcompare" ? styles.active : ""}`}
                onClick={() => selectTab("dbcompare")}
              >
                Comparador BD
              </button>
            )}
            {costCenterEnabled && (
              <button
                className={`${styles.navTab} ${tab === "costcenter" ? styles.active : ""}`}
                onClick={() => selectTab("costcenter")}
              >
                💰 Centro de Costos
              </button>
            )}
            {planesEnabled && (
              <button
                className={`${styles.navTab} ${tab === "planes" ? styles.active : ""}`}
                onClick={() => selectTab("planes")}
              >
                🧭 Planes
              </button>
            )}
            {evolutionEnabled && (
              <button
                className={`${styles.navTab} ${tab === "evolution" ? styles.active : ""}`}
                onClick={() => selectTab("evolution")}
              >
                🧬 Evolución
              </button>
            )}
          </nav>

          <PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>
        </>
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={navigateTo}
        deepSearchEnabled={deepSearchEnabled}
      />
      <ShortcutsCheatsheet
        open={cheatsheetOpen}
        onClose={() => setCheatsheetOpen(false)}
      />
      <DailyStandupModal />
      <OnboardingTour />

      {/* Plan 185 — host global de toasts de "Deshacer" (undo universal con
          gracia). Capa 2 esquina inferior derecha; ver tabla 197 §6.11. */}
      <UndoToastHost />

      {/* Consola flotante de runtimes CLI (Codex / Claude): muestra la actividad
          en vivo y permite responderle al agente. Se activa al lanzar un run CLI. */}
      <CodexConsoleDock />

      {/* Panel global de ejecuciones activas: permite cancelar manualmente
          cualquier run en curso (incluidos huérfanos/colgados de otro proyecto
          que el board no muestra). Solo aparece si hay runs activos. */}
      <ActiveRunsPanel />
    </div>
  );
}

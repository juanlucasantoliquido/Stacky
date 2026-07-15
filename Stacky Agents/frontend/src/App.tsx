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
import TopBar from "./components/TopBar";
import HealthBanner from "./components/HealthBanner";
import CommandPalette from "./components/CommandPalette";
import DailyStandupModal from "./components/DailyStandupModal";
import OnboardingTour from "./components/OnboardingTour";
import ShortcutsCheatsheet from "./components/ShortcutsCheatsheet";
import DemoModeBanner from "./components/DemoModeBanner";
import CodexConsoleDock from "./components/CodexConsoleDock";
import ActiveRunsPanel from "./components/ActiveRunsPanel";
import PageErrorBoundary from "./components/PageErrorBoundary";
import { probeFlagHealth, nextEnabledState } from "./utils/flagHealth";
import { toggleNavTab } from "./services/uiGuards";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import { useGlobalExecutionNotifier } from "./hooks/useGlobalExecutionNotifier";
import { useReviewInboxCount } from "./hooks/useReviewInboxCount";
import { reviewBadgeLabel } from "./services/reviewInbox";
import AppSidebar from "./components/shell/AppSidebar";
import {
  computeVisibleTabs, parseCollapsed, SIDEBAR_COLLAPSED_KEY,
} from "./components/shell/shellNav";
import styles from "./App.module.css";

type Tab = "team" | "tickets" | "review" | "unblocker" | "pm" | "logs" | "settings" | "docs" | "memory" | "diagnostics" | "history" | "migrador" | "devops" | "dbcompare" | "costcenter";

const TAB_PATHS: Record<Tab, string> = {
  team: "/",
  tickets: "/tickets",
  review: "/review",
  unblocker: "/unblocker",
  pm: "/pm",
  logs: "/logs",
  settings: "/settings",
  docs: "/docs",
  memory: "/memory",
  diagnostics: "/diagnostics",
  history: "/history",
  migrador: "/migrador",
  devops: "/devops",
  dbcompare: "/dbcompare", // Plan 122 [FIX C3]
  costcenter: "/costcenter", // Plan 142
};

function tabFromPath(pathname: string): Tab {
  const found = (Object.entries(TAB_PATHS) as [Tab, string][])
    .find(([, path]) => path !== "/" && pathname.startsWith(path));
  return found?.[0] ?? "team";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => tabFromPath(window.location.pathname));
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

  useGlobalExecutionNotifier();
  const reviewCount = useReviewInboxCount();
  const reviewBadge = reviewBadgeLabel(reviewCount);

  const selectTab = (next: Tab) => {
    setTab(next);
    const path = TAB_PATHS[next];
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
  };

  const navigateTo = (path: string) => {
    const targetTab = tabFromPath(path);
    setTab(targetTab);
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
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

  useEffect(() => {
    const onPopState = () => setTab(tabFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
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
  // fallback a "team" para no quedar en blanco.
  useEffect(() => {
    if (tab === "pm" && !sections.pm) selectTab("team");
    else if (tab === "logs" && !sections.logs) selectTab("team");
    else if (tab === "docs" && !sections.docs) selectTab("team");
    else if (tab === "memory" && !sections.memory) selectTab("team");
    else if (tab === "migrador" && !migradorEnabled) selectTab("team");
    else if (tab === "devops" && !devopsEnabled) selectTab("team");
    else if (tab === "dbcompare" && !dbCompareEnabled) selectTab("team");
    else if (tab === "costcenter" && !costCenterEnabled) selectTab("team");
  }, [tab, sections.pm, sections.logs, sections.docs, sections.memory, migradorEnabled, devopsEnabled, dbCompareEnabled, costCenterEnabled]);

  const visibleTabs = computeVisibleTabs({
    sections: {
      pm: !!sections.pm, logs: !!sections.logs,
      docs: !!sections.docs, memory: !!sections.memory,
    },
    migradorEnabled, devopsEnabled, dbCompareEnabled, costCenterEnabled,
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
      {tab === "team"     && <TeamScreen />}
      {tab === "tickets"  && <TicketBoard />}
      {tab === "review"   && <ReviewInboxPage />}
      {tab === "unblocker" && <UnblockerPage />}
      {tab === "pm"       && sections.pm   && <PMCommandCenter />}
      {tab === "logs"     && sections.logs && <SystemLogsPage />}
      {tab === "settings" && <SettingsPage />}
      {tab === "docs"     && sections.docs && <DocsPage />}
      {tab === "memory"   && sections.memory && <MemoryPage />}
      {tab === "diagnostics" && <DiagnosticsPage />}
      {tab === "history"     && <ExecutionHistoryPage />}
      {tab === "migrador"    && migradorEnabled && <MigratorPage />} {/* Plan 74 */}
      {tab === "devops"      && devopsEnabled && <DevOpsPage />} {/* Plan 87 */}
      {tab === "dbcompare"   && dbCompareEnabled && <DbComparePage />} {/* Plan 122 */}
      {tab === "costcenter"  && costCenterEnabled && <CostCenterPage />} {/* Plan 142 */}
    </>
  );

  return (
    <div className={styles.appRoot}>
      <DemoModeBanner />
      <TopBar onGoToTeam={() => selectTab("team")} shellV2={shellV2Enabled} />
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
          <nav className={styles.nav}>
            <button
              className={`${styles.navTab} ${tab === "team" ? styles.active : ""}`}
              onClick={() => selectTab("team")}
            >
              ⚡ Mi Equipo
            </button>
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
          </nav>

          <PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>
        </>
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={navigateTo}
      />
      <ShortcutsCheatsheet
        open={cheatsheetOpen}
        onClose={() => setCheatsheetOpen(false)}
      />
      <DailyStandupModal />
      <OnboardingTour />

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

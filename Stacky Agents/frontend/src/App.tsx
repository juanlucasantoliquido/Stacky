import { useEffect, useState } from "react";
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
import TopBar from "./components/TopBar";
import HealthBanner from "./components/HealthBanner";
import CommandPalette from "./components/CommandPalette";
import DailyStandupModal from "./components/DailyStandupModal";
import OnboardingTour from "./components/OnboardingTour";
import ShortcutsCheatsheet from "./components/ShortcutsCheatsheet";
import DemoModeBanner from "./components/DemoModeBanner";
import CodexConsoleDock from "./components/CodexConsoleDock";
import ActiveRunsPanel from "./components/ActiveRunsPanel";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import { useGlobalExecutionNotifier } from "./hooks/useGlobalExecutionNotifier";
import styles from "./App.module.css";

type Tab = "team" | "tickets" | "review" | "unblocker" | "pm" | "logs" | "settings" | "docs" | "memory" | "diagnostics" | "history" | "migrador" | "devops";

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
};

function tabFromPath(pathname: string): Tab {
  const found = (Object.entries(TAB_PATHS) as [Tab, string][])
    .find(([, path]) => path !== "/" && pathname.startsWith(path));
  return found?.[0] ?? "team";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => tabFromPath(window.location.pathname));
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);
  const sections = useUiSectionsStore((s) => s.sections);
  // Plan 74: tab migrador visible solo si el flag está ON en el backend
  const [migradorEnabled, setMigradorEnabled] = useState(false);
  // Plan 87: tab DevOps visible solo si el flag está ON en el backend
  const [devopsEnabled, setDevopsEnabled] = useState(false);
  // Plan 129: búsqueda profunda de la paleta (Ctrl+K) solo si el flag está ON en el backend
  const [deepSearchEnabled, setDeepSearchEnabled] = useState(false);

  useGlobalExecutionNotifier();

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
    // Plan 74: comprobar si el migrador está habilitado (flag backend)
    fetch("/api/migrator/health")
      .then((r) => r.json())
      .then((d: { flag_enabled?: boolean }) => setMigradorEnabled(d.flag_enabled === true))
      .catch(() => setMigradorEnabled(false));
    // Plan 87: comprobar si DevOps está habilitado (flag backend)
    fetch("/api/devops/health")
      .then((r) => r.json())
      .then((d: { flag_enabled?: boolean }) => setDevopsEnabled(d.flag_enabled === true))
      .catch(() => setDevopsEnabled(false));
    // Plan 129: comprobar si la búsqueda profunda de la paleta está habilitada (flag backend)
    fetch("/api/search/health")
      .then((r) => r.json())
      .then((d: { flag_enabled?: boolean }) => setDeepSearchEnabled(d.flag_enabled === true))
      .catch(() => setDeepSearchEnabled(false));
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
        setTab((t) => (t === "team" ? "tickets" : "team"));
        const path = TAB_PATHS[tab === "team" ? "tickets" : "team"];
        window.history.pushState({}, "", path);
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
  }, [tab, sections.pm, sections.logs, sections.docs, sections.memory, migradorEnabled, devopsEnabled]);

  return (
    <div className={styles.appRoot}>
      <DemoModeBanner />
      <TopBar onGoToTeam={() => selectTab("team")} />
      <HealthBanner />

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
      </nav>

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

import { useEffect, useState } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import SystemLogsPage from "./pages/SystemLogsPage";
import PMCommandCenter from "./pages/PMCommandCenter";
import SettingsPage from "./pages/SettingsPage";
import DocsPage from "./pages/DocsPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import TopBar from "./components/TopBar";
import { initPreferences } from "./services/preferences";
import { initUiSections } from "./services/uiSections";
import { useUiSectionsStore } from "./store/uiSectionsStore";
import styles from "./App.module.css";

type Tab = "team" | "tickets" | "pm" | "logs" | "settings" | "docs" | "diagnostics";

const TAB_PATHS: Record<Tab, string> = {
  team: "/",
  tickets: "/tickets",
  pm: "/pm",
  logs: "/logs",
  settings: "/settings",
  docs: "/docs",
  diagnostics: "/diagnostics",
};

function tabFromPath(pathname: string): Tab {
  const found = (Object.entries(TAB_PATHS) as [Tab, string][])
    .find(([, path]) => path !== "/" && pathname.startsWith(path));
  return found?.[0] ?? "team";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => tabFromPath(window.location.pathname));
  const sections = useUiSectionsStore((s) => s.sections);

  const selectTab = (next: Tab) => {
    setTab(next);
    const path = TAB_PATHS[next];
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
  };

  useEffect(() => {
    initPreferences();
    initUiSections();
  }, []);

  useEffect(() => {
    const onPopState = () => setTab(tabFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Si el usuario tenía seleccionado un tab opcional que acaba de ocultarse,
  // fallback a "team" para no quedar en blanco.
  useEffect(() => {
    if (tab === "pm" && !sections.pm) selectTab("team");
    else if (tab === "logs" && !sections.logs) selectTab("team");
    else if (tab === "docs" && !sections.docs) selectTab("team");
  }, [tab, sections.pm, sections.logs, sections.docs]);

  return (
    <div className={styles.appRoot}>
      <TopBar onGoToTeam={() => selectTab("team")} />

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
        <button
          className={`${styles.navTab} ${tab === "diagnostics" ? styles.active : ""}`}
          onClick={() => selectTab("diagnostics")}
        >
          🩺 Diagnóstico
        </button>
      </nav>

      {tab === "team"     && <TeamScreen />}
      {tab === "tickets"  && <TicketBoard />}
      {tab === "pm"       && sections.pm   && <PMCommandCenter />}
      {tab === "logs"     && sections.logs && <SystemLogsPage />}
      {tab === "settings" && <SettingsPage />}
      {tab === "docs"     && sections.docs && <DocsPage />}
      {tab === "diagnostics" && <DiagnosticsPage />}
    </div>
  );
}

import { useEffect, useState } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import SystemLogsPage from "./pages/SystemLogsPage";
import PMCommandCenter from "./pages/PMCommandCenter";
import FlowConfigPage from "./pages/FlowConfigPage";
import DocsPage from "./pages/DocsPage";
import TopBar from "./components/TopBar";
import { initPreferences } from "./services/preferences";
import styles from "./App.module.css";

type Tab = "team" | "tickets" | "pm" | "logs" | "flow-config" | "docs";

export default function App() {
  const [tab, setTab] = useState<Tab>("team");

  useEffect(() => {
    initPreferences();
  }, []);

  return (
    <div className={styles.appRoot}>
      <TopBar onGoToTeam={() => setTab("team")} />

      {/* Tabs de navegación principal */}
      <nav className={styles.nav}>
        <button
          className={`${styles.navTab} ${tab === "team" ? styles.active : ""}`}
          onClick={() => setTab("team")}
        >
          ⚡ Mi Equipo
        </button>
        <button
          className={`${styles.navTab} ${tab === "tickets" ? styles.active : ""}`}
          onClick={() => setTab("tickets")}
        >
          📋 Tickets ADO
        </button>
        <button
          className={`${styles.navTab} ${tab === "pm" ? styles.active : ""}`}
          onClick={() => setTab("pm")}
        >
          📊 PM
        </button>
        <button
          className={`${styles.navTab} ${tab === "logs" ? styles.active : ""}`}
          onClick={() => setTab("logs")}
        >
          🔍 System Logs
        </button>
        <button
          className={`${styles.navTab} ${tab === "flow-config" ? styles.active : ""}`}
          onClick={() => setTab("flow-config")}
        >
          ⚙️ Config de Flujo
        </button>
        <button
          className={`${styles.navTab} ${tab === "docs" ? styles.active : ""}`}
          onClick={() => setTab("docs")}
        >
          📄 Docs
        </button>
      </nav>

      {tab === "team"        && <TeamScreen />}
      {tab === "tickets"     && <TicketBoard />}
      {tab === "pm"          && <PMCommandCenter />}
      {tab === "logs"        && <SystemLogsPage />}
      {tab === "flow-config" && <FlowConfigPage />}
      {tab === "docs"        && <DocsPage />}
    </div>
  );
}

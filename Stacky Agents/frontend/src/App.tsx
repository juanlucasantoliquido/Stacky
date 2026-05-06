import { useEffect, useState } from "react";
import TeamScreen from "./pages/TeamScreen";
import TicketBoard from "./pages/TicketBoard";
import SystemLogsPage from "./pages/SystemLogsPage";
import { initPreferences } from "./services/preferences";
import styles from "./App.module.css";

type Tab = "team" | "tickets" | "logs";

export default function App() {
  const [tab, setTab] = useState<Tab>("team");

  useEffect(() => {
    initPreferences();
  }, []);

  return (
    <div className={styles.appRoot}>
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
          className={`${styles.navTab} ${tab === "logs" ? styles.active : ""}`}
          onClick={() => setTab("logs")}
        >
          🔍 System Logs
        </button>
      </nav>

      {tab === "team"    && <TeamScreen />}
      {tab === "tickets" && <TicketBoard />}
      {tab === "logs"    && <SystemLogsPage />}
    </div>
  );
}

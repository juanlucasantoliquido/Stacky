import { useWorkbench } from "../store/workbench";
import styles from "./TopBar.module.css";

interface TopBarProps {
  onGoToTeam?: () => void;
}

export default function TopBar({ onGoToTeam }: TopBarProps) {
  const runningExecutionId = useWorkbench((s) => s.runningExecutionId);
  const isRunning = runningExecutionId != null;

  return (
    <header className={styles.bar}>
      <div className={styles.main}>
        <div className={styles.brand}>
          {onGoToTeam && (
            <button className={styles.teamBtn} onClick={onGoToTeam} title="Volver al equipo">
              ← Equipo
            </button>
          )}
          <img
            src="/stacky-agents-logo.svg"
            alt="Stacky"
            className={styles.logoImg}
            width={22}
            height={22}
          />
          Stacky
        </div>
        <div className={styles.project}>
          Project <strong>Strategist_Pacifico</strong>
        </div>
        <div className={styles.actions}>
          {isRunning && (
            <span className={styles.runningBadge}>
              <span className={styles.badgeSpinner} aria-hidden="true" />
              Agente trabajando…
            </span>
          )}
          <span>dev@local</span>
        </div>
      </div>
      {isRunning && <div className={styles.progressBar} role="progressbar" aria-label="Ejecución en progreso" />}
    </header>
  );
}

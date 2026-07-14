import type { CompareRun } from "./dbcompareTypes";
import { relativeTimeEs } from "./relativeTime";
import styles from "./dbcompare.module.css";

interface Props {
  runs: CompareRun[];
  activeRunId: string | null;
  onSelectRun: (run: CompareRun) => void;
}

/** Plan 124 F6 — historial de corridas: banda horizontal con re-apertura 1-click. La corrida
 * activa (running) aparece primera. Tiempo relativo vía relativeTime.ts (ya testeado). */
export function RunsTimeline({ runs, activeRunId, onSelectRun }: Props) {
  if (runs.length === 0) {
    return <div className={styles.emptyState}>Elegí origen y destino y lanzá tu primera comparación.</div>;
  }

  const nowIso = new Date().toISOString();
  const sorted = [...runs].sort((a, b) => (a.status === "running" ? -1 : b.status === "running" ? 1 : 0));

  return (
    <div className={styles.runsTimeline}>
      {sorted.map((run) => (
        <div
          key={run.run_id}
          className={`${styles.runCard} ${run.run_id === activeRunId ? styles.runCardActive : ""}`}
          onClick={() => onSelectRun(run)}
        >
          <div>
            {run.source_alias} → {run.target_alias}
          </div>
          <div className={styles.recency}>
            {run.status === "running" ? "en curso…" : relativeTimeEs(run.finished_at ?? run.started_at, nowIso)}
          </div>
          {run.summary && (
            <div className={styles.recency}>
              {run.summary.parity_score}% · 🔴{run.summary.by_severity.danger} 🟠
              {run.summary.by_severity.warn} 🔵{run.summary.by_severity.info}
            </div>
          )}
          {run.stale && <span className={styles.staleCard}>stale</span>}
          {run.status === "error" && <span className={styles.errorBanner}>error</span>}
        </div>
      ))}
    </div>
  );
}

export default RunsTimeline;

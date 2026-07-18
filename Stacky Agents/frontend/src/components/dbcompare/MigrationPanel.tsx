// Plan 157 F6 — Panel de Migración de BD siempre visible: selector de corridas
// `done` + "Generar/ver scripts" + "Descargar bundle .zip", sin pegar run_id.
// NO es el tab "Migrador" (ADO→GitLab, Plan 74): es la migración de esquema/datos
// entre ambientes, materializada como scripts que el operador ejecuta (Stacky nunca
// ejecuta). Reusa ScriptsPanel como visor inline.
import { useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { CompareRun } from "./dbcompareTypes";
import { selectableRuns } from "./migrationPanelLogic";
import { relativeTimeEs } from "./relativeTime";
import { ScriptsPanel } from "./ScriptsPanel";
import styles from "./dbcompare.module.css";

interface Props {
  runs: CompareRun[];
}

export function MigrationPanel({ runs }: Props) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const done = selectableRuns(runs);
  const nowIso = new Date().toISOString();

  return (
    <section className={styles.migrationPanel}>
      <h2>Migración de BD (scripts de paridad + backups)</h2>
      <p className={styles.subtitle}>
        Elegí una corrida terminada para generar/ver sus scripts de paridad + backups
        pareados 1:1 y descargar el bundle. Stacky genera; jamás ejecuta.
      </p>
      {done.length === 0 && (
        <div className={styles.emptyState}>Todavía no hay corridas terminadas para migrar.</div>
      )}
      {done.map((run) => (
        <div key={run.run_id} className={styles.migrationRow}>
          <span>
            <strong>{run.source_alias}</strong> → <strong>{run.target_alias}</strong>
          </span>
          <span className={styles.recency}>
            {relativeTimeEs(run.finished_at || run.started_at, nowIso)}
          </span>
          <span className={styles.migrationRowActions}>
            <button onClick={() => setSelectedRunId(run.run_id)}>Generar/ver scripts</button>
            <button onClick={() => DbCompare.downloadScriptsZip(run.run_id)}>
              Descargar bundle .zip
            </button>
          </span>
        </div>
      ))}
      {selectedRunId && <ScriptsPanel key={selectedRunId} runId={selectedRunId} />}
    </section>
  );
}

export default MigrationPanel;

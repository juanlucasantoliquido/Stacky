import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { DbCompareHealth } from "./dbcompareTypes";
import { EnvironmentsPanel } from "./EnvironmentsPanel";
import { ScriptsPanel } from "./ScriptsPanel";
import styles from "./dbcompare.module.css";

/**
 * Plan 122 F5 — tab "Comparador BD": header con estado de drivers + gestión de
 * ambientes. La inmersión visual completa (wizard, gauge, treemap, drill-down)
 * llega en el Plan 124; esta sección nace funcional y sobria.
 */
export function DbComparePage() {
  const [health, setHealth] = useState<DbCompareHealth | null>(null);
  const [runIdInput, setRunIdInput] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  useEffect(() => {
    DbCompare.health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const missingDrivers = health
    ? Object.entries(health.drivers).filter(([, info]) => !info.available)
    : [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Comparador de BD entre ambientes</h1>
        <p className={styles.subtitle}>
          Registrá ambientes de BD (solo lectura), tomá snapshots de esquema y compará
          drift entre ellos. Stacky genera, nunca ejecuta.
        </p>
      </header>

      {missingDrivers.length > 0 && (
        <div className={styles.driverWarning}>
          {missingDrivers.map(([engine, info]) => (
            <div key={engine} className={styles.driverWarningRow}>
              <strong>{engine}</strong>: falta el driver <code>{info.module}</code>.
              <br />
              Instalalo con: <code>{info.install_hint}</code>
            </div>
          ))}
        </div>
      )}

      <EnvironmentsPanel keyringAvailable={health?.keyring_available ?? true} />

      <section className={styles.scriptsSection}>
        <h2>Scripts de paridad (Plan 125)</h2>
        <p className={styles.subtitle}>
          Pegá el ID de una corrida ya terminada (<code>done</code>) para generar y ver sus
          scripts de paridad + backups pareados 1:1. El listado visual de corridas (Plan 124)
          todavía no está montado acá; por ahora se busca por ID.
        </p>
        <div className={styles.runIdRow}>
          <input
            value={runIdInput}
            onChange={(e) => setRunIdInput(e.target.value)}
            placeholder="run_20260714T120000Z_DEV_vs_TEST"
          />
          <button
            onClick={() => setActiveRunId(runIdInput.trim() || null)}
            disabled={!runIdInput.trim()}
          >
            Ver scripts
          </button>
        </div>
        {activeRunId && <ScriptsPanel key={activeRunId} runId={activeRunId} />}
      </section>
    </div>
  );
}

export default DbComparePage;

import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { DbCompareHealth } from "./dbcompareTypes";
import { EnvironmentsPanel } from "./EnvironmentsPanel";
import styles from "./dbcompare.module.css";

/**
 * Plan 122 F5 — tab "Comparador BD": header con estado de drivers + gestión de
 * ambientes. La inmersión visual completa (wizard, gauge, treemap, drill-down)
 * llega en el Plan 124; esta sección nace funcional y sobria.
 */
export function DbComparePage() {
  const [health, setHealth] = useState<DbCompareHealth | null>(null);

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
    </div>
  );
}

export default DbComparePage;

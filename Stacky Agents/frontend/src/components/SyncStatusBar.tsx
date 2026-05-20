/**
 * SyncStatusBar — Indicador visual del estado de sincronizacion con ADO.
 *
 * P7: Muestra en tiempo real cuando fue el ultimo sync, si hay error,
 * si el dato esta desactualizado (stale), y un boton de sincronizacion manual.
 *
 * Estados visuales:
 * - Syncing:          spinner + "Sincronizando con ADO..."
 * - OK reciente (<60s): punto verde + "Sincronizado hace X seg"
 * - OK envejeciendo (60s–2*intervalMs): punto amarillo
 * - Stale (> 2*intervalMs): punto rojo + "Sin actualizar hace X min"
 * - Error: punto rojo + mensaje corto + boton Reintentar
 */

import React from "react";
import styles from "./SyncStatusBar.module.css";

interface SyncStatusBarProps {
  lastSyncedAt: string | null;
  secondsSinceSync: number | null;
  isSyncing: boolean;
  syncError: string | null;
  onSyncClick: () => void;
  isStale: boolean;
  intervalMs?: number;
}

function formatSeconds(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `${min}m ${s}s` : `${min}m`;
}

export function SyncStatusBar({
  lastSyncedAt,
  secondsSinceSync,
  isSyncing,
  syncError,
  onSyncClick,
  isStale,
  intervalMs = 45_000,
}: SyncStatusBarProps): React.ReactElement {
  const agingThresholdSec = 60;

  if (isSyncing) {
    return (
      <div className={styles.bar}>
        <span className={styles.spinner} />
        <span className={styles.label}>Sincronizando con ADO...</span>
      </div>
    );
  }

  if (syncError) {
    return (
      <div className={styles.bar}>
        <span className={`${styles.dot} ${styles.red}`} />
        <span className={`${styles.label} ${styles.labelError}`}>
          Error de sincronizacion: {syncError.slice(0, 80)}
        </span>
        <button className={styles.btn} onClick={onSyncClick}>
          Reintentar
        </button>
      </div>
    );
  }

  if (!lastSyncedAt || secondsSinceSync === null) {
    return (
      <div className={styles.bar}>
        <span className={`${styles.dot} ${styles.yellow}`} />
        <span className={styles.label}>Sin sincronizar</span>
        <button className={styles.btn} onClick={onSyncClick}>
          Sincronizar ADO
        </button>
      </div>
    );
  }

  if (isStale) {
    return (
      <div className={styles.bar}>
        <span className={`${styles.dot} ${styles.red}`} />
        <span className={`${styles.label} ${styles.labelStale}`}>
          Sin actualizar hace {formatSeconds(secondsSinceSync)} — datos pueden estar desactualizados
        </span>
        <button className={styles.btn} onClick={onSyncClick}>
          Sincronizar ahora
        </button>
      </div>
    );
  }

  const dotColor = secondsSinceSync < agingThresholdSec ? styles.green : styles.yellow;

  return (
    <div className={styles.bar}>
      <span className={`${styles.dot} ${dotColor}`} />
      <span className={styles.label}>
        Sincronizado hace {formatSeconds(secondsSinceSync)}
      </span>
      <button className={styles.btn} onClick={onSyncClick}>
        Sincronizar
      </button>
    </div>
  );
}

export default SyncStatusBar;

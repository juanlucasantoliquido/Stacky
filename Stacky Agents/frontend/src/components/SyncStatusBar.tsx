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
import { secondsSince, isStaleAt } from "./syncStatus";

interface SyncStatusBarProps {
  lastSyncedAt: string | null;
  isSyncing: boolean;
  syncError: string | null;
  onSyncClick: () => void;
  intervalMs?: number;
}

function formatSeconds(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `${min}m ${s}s` : `${min}m`;
}

function SyncStatusBarBase({
  lastSyncedAt,
  isSyncing,
  syncError,
  onSyncClick,
  intervalMs = 45_000,
}: SyncStatusBarProps): React.ReactElement {
  const agingThresholdSec = 60;

  // Plan 156 F4 — el reloj de 1s vive ACÁ (en la hoja), no en useTicketSync.
  // React.memo (abajo) evita que este tic-tac suba y re-renderice el board.
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const ticker = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(ticker);
  }, []);
  const secondsSinceSync = secondsSince(lastSyncedAt, now);
  const isStale = isStaleAt(lastSyncedAt, intervalMs, now);

  if (isSyncing) {
    return (
      <div className={styles.wrap}>
        <div className={`${styles.bar} ${styles.toneNeutral}`}>
          <span className={styles.spinner} />
          <span className={styles.label}>Sincronizando con ADO…</span>
        </div>
      </div>
    );
  }

  if (syncError) {
    return (
      <div className={styles.wrap}>
        <div className={`${styles.bar} ${styles.toneDanger}`}>
          <span className={`${styles.dot} ${styles.red}`} />
          <span className={`${styles.label} ${styles.labelError}`} title={syncError}>
            Error de sincronización
          </span>
          <button className={styles.btn} onClick={onSyncClick}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (!lastSyncedAt || secondsSinceSync === null) {
    return (
      <div className={styles.wrap}>
        <div className={`${styles.bar} ${styles.toneNeutral}`}>
          <span className={`${styles.dot} ${styles.yellow}`} />
          <span className={styles.label}>Sin sincronizar</span>
          <button className={styles.btn} onClick={onSyncClick}>
            Sincronizar
          </button>
        </div>
      </div>
    );
  }

  if (isStale) {
    return (
      <div className={styles.wrap}>
        <div className={`${styles.bar} ${styles.toneWarning}`}>
          <span className={`${styles.dot} ${styles.red}`} />
          <span className={`${styles.label} ${styles.labelStale}`}>
            Sin actualizar hace {formatSeconds(secondsSinceSync)}
          </span>
          <button className={styles.btn} onClick={onSyncClick}>
            Actualizar
          </button>
        </div>
      </div>
    );
  }

  const dotColor = secondsSinceSync < agingThresholdSec ? styles.green : styles.yellow;

  return (
    <div className={styles.wrap}>
      <div className={`${styles.bar} ${styles.toneNeutral}`}>
        <span className={`${styles.dot} ${dotColor}`} />
        <span className={styles.label}>
          Sincronizado hace {formatSeconds(secondsSinceSync)}
        </span>
        <button className={styles.btn} onClick={onSyncClick}>
          Sincronizar
        </button>
      </div>
    </div>
  );
}

// Plan 156 F4 — memoizado: el tic-tac de 1s propio NO debe re-renderizar al padre.
export const SyncStatusBar = React.memo(SyncStatusBarBase);
export default SyncStatusBar;

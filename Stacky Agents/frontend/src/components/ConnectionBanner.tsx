import { useEffect, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "./ui";
import { apiBase } from "../api/client";
import { connectionMonitor } from "../services/connectionMonitor";
import { makeRecoveryHandler } from "../services/connectionRecovery";
import {
  isConnectionResilienceEnabled,
  readCachedConnectionFlag,
} from "../services/connectionFlags";
import { computeBannerView } from "../services/connectionBanner.logic";
import styles from "./ConnectionBanner.module.css";

export default function ConnectionBanner() {
  const queryClient = useQueryClient();
  const [flagOn, setFlagOn] = useState<boolean>(() => readCachedConnectionFlag());

  useEffect(() => {
    let alive = true;
    isConnectionResilienceEnabled().then((v) => {
      if (alive) setFlagOn(v);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!flagOn) return;
    connectionMonitor.setOnRecovered(makeRecoveryHandler(queryClient));
    connectionMonitor.enable({ probeUrl: `${apiBase}/api/diag/health` });
    return () => {
      connectionMonitor.disable();
      connectionMonitor.setOnRecovered(null);
    };
  }, [flagOn, queryClient]);

  const snapshot = useSyncExternalStore(
    connectionMonitor.subscribe,
    connectionMonitor.getSnapshot,
  );
  const view = computeBannerView(snapshot);
  if (!flagOn) return null;

  return (
    <>
      {/* Live region PERSISTENTE (announcer C12): cambia su TEXTO, nunca se monta y
          desmonta con el banner (una region insertada ya con contenido puede no anunciarse). */}
      <span role="status" aria-live="polite" className={styles.srOnly}>
        {view.visible ? view.message : ""}
      </span>
      {view.visible ? (
        <div
          className={
            view.kind === "recovering"
              ? `${styles.banner} ${styles.recovering}`
              : `${styles.banner} ${styles.down}`
          }
        >
          <span aria-hidden="true" className={styles.msg}>
            {view.message}
          </span>
          {view.attemptText ? (
            <span aria-hidden="true" className={styles.attempt}>
              {view.attemptText}
            </span>
          ) : null}
          {view.showRetry ? (
            <Button onClick={() => connectionMonitor.probeNow()}>Reintentar ahora</Button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

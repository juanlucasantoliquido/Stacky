import { useEffect, useState, useSyncExternalStore } from "react";
import { connectionMonitor } from "../services/connectionMonitor";
import {
  isConnectionResilienceEnabled,
  readCachedConnectionFlag,
} from "../services/connectionFlags";
import { freshnessLabel } from "../services/connectionBanner.logic";
import styles from "./ConnectionFreshnessDot.module.css";

export default function ConnectionFreshnessDot() {
  const [flagOn, setFlagOn] = useState<boolean>(() => readCachedConnectionFlag());
  const [, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    isConnectionResilienceEnabled().then((v) => {
      if (alive) setFlagOn(v);
    });
    return () => {
      alive = false;
    };
  }, []);
  const snapshot = useSyncExternalStore(
    connectionMonitor.subscribe,
    connectionMonitor.getSnapshot,
  );
  if (!flagOn || !snapshot.enabled) return null;
  const cls =
    snapshot.status === "healthy"
      ? styles.ok
      : snapshot.status === "recovering"
        ? styles.warn
        : styles.bad;
  // C3: el title usa la lectura VIVA getLastOkAt() (no snapshot.lastOkAt, que solo
  // se regenera al transicionar y en healthy sostenido quedaria congelado).
  return (
    <span
      className={`${styles.dot} ${cls}`}
      title={freshnessLabel(connectionMonitor.getLastOkAt(), Date.now())}
      aria-hidden="true"
      onMouseEnter={() => setTick((t) => t + 1)}
    />
  );
}

import { useEffect, useState } from "react";
import { isDemoMode, setDemoMode, subscribeDemoMode } from "../store/demoMode";
import styles from "./DemoModeBanner.module.css";

export default function DemoModeBanner() {
  const [enabled, setEnabled] = useState(isDemoMode());

  useEffect(() => {
    return subscribeDemoMode(setEnabled);
  }, []);

  if (!enabled) return null;

  return (
    <div className={styles.banner} role="status">
      <span className={styles.dots} aria-hidden="true">D E M O</span>
      <span className={styles.label}>MODO DEMO — outputs cacheados, sin riesgo de filtrar data real</span>
      <button
        className={styles.exitBtn}
        onClick={() => setDemoMode(false)}
        title="Salir del modo demo"
      >
        Salir
      </button>
    </div>
  );
}

export function DemoModeToggle() {
  const [enabled, setEnabled] = useState(isDemoMode());
  useEffect(() => subscribeDemoMode(setEnabled), []);
  return (
    <label className={styles.toggle}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => setDemoMode(e.target.checked)}
      />
      <span>Modo Demo</span>
    </label>
  );
}

import { useCallback, useEffect, useState } from "react";
import { DbCompareDemo } from "../../api/endpoints";
import type { DbEnvironment } from "./dbcompareTypes";
import { demoPanelState, type DemoStatus } from "./demoLogic";
import { useConfirm } from "../ui";
import styles from "./dbcompare.module.css";

interface Props {
  environments: DbEnvironment[];
  onChanged: () => void;
}

/**
 * Plan 183 F4 — panel del sandbox de demostración del comparador. CTA de 1 click
 * para sembrar un par sqlite de ejemplo (sin credenciales/red), banner "Quitar demo"
 * con confirmación, y estado `demo-broken` con "Re-sembrar" (fix C6). Se auto-oculta
 * ante 403/red (patrón health → null, KPI-4). Sin estilos inline (uiDebtRatchet): solo clases del module.css.
 */
export function DemoSandboxPanel({ environments, onChanged }: Props) {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [visible, setVisible] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const askConfirm = useConfirm();

  const refresh = useCallback(async () => {
    try {
      const r = await DbCompareDemo.status();
      setStatus(r.status);
      setVisible(true);
    } catch {
      // 403 (flag off) o red caída ⇒ el panel desaparece.
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runAction = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
      onChanged();
    } catch (err) {
      // 409 (archivos lockeados, fix C3) / 503 (keyring) / 500: mostrar sin crash.
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSeed = () => runAction(() => DbCompareDemo.seed());
  const handleRemove = async () => {
    const ok = await askConfirm({
      title: "Quitar ambientes de demostración",
      message: "¿Quitar los ambientes de demostración? Se borran solo los archivos del sandbox.",
      tone: "danger",
      confirmLabel: "Quitar",
    });
    if (!ok) return;
    void runAction(() => DbCompareDemo.remove());
  };

  if (!visible || status === null) {
    return null;
  }

  const state = demoPanelState(environments, status);
  const ctaSubtitle = "Crea un par sqlite local con drift de ejemplo. Sin credenciales, sin red.";

  if (state === "demo-broken") {
    return (
      <div className={styles.demoBroken}>
        <div>
          <strong>El sandbox de demostración quedó a medias</strong>
          <div className={styles.demoSubtitle}>
            Archivos y registro están desincronizados. Re-sembrá para repararlo.
          </div>
        </div>
        <div className={styles.demoActions}>
          <button onClick={handleSeed} disabled={busy}>
            {busy ? "Trabajando…" : "Re-sembrar"}
          </button>
        </div>
        {error && <div className={styles.demoError}>{error}</div>}
      </div>
    );
  }

  if (state === "demo-active") {
    return (
      <div className={styles.demoBanner}>
        <div>
          <strong>Ambientes de demostración activos</strong>
          <div className={styles.demoSubtitle}>
            <code>test-demo-dev</code> → <code>test-demo-test</code>
          </div>
        </div>
        <div className={styles.demoActions}>
          <button onClick={handleRemove} disabled={busy}>
            {busy ? "Trabajando…" : "Quitar demo"}
          </button>
        </div>
        {error && <div className={styles.demoError}>{error}</div>}
      </div>
    );
  }

  // cta-empty (prominente) | cta-secondary (discreto)
  const containerClass = state === "cta-empty" ? styles.demoCta : styles.demoSecondary;
  return (
    <div className={containerClass}>
      <div>
        <strong>Probar con ambientes de ejemplo</strong>
        <div className={styles.demoSubtitle}>{ctaSubtitle}</div>
      </div>
      <div className={styles.demoActions}>
        <button onClick={handleSeed} disabled={busy}>
          {busy ? "Sembrando…" : "Probar con ambientes de ejemplo"}
        </button>
      </div>
      {error && <div className={styles.demoError}>{error}</div>}
    </div>
  );
}

export default DemoSandboxPanel;

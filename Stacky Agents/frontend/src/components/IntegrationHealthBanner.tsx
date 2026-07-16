import { useEffect, useState } from "react";
import { Integrations, type IntegrationHealthItem } from "../api/endpoints";
import { resolveVisibleIntegrations, shouldRenderBanner } from "./integrationHealth.logic";
import styles from "./IntegrationHealthBanner.module.css";

/**
 * IntegrationHealthBanner — Plan 148 F6.
 *
 * Tira discreta que SOLO aparece cuando alguna integración (ADO/Jira/LLM local)
 * está degradada (circuit-breaker abierto). Si no hay ninguna caída, no
 * renderiza nada (cero ruido cuando todo está sano). Reusa el patrón de
 * polling + navegación cross-page de HealthBanner.tsx.
 */

const POLL_MS = 60_000;

function goToVault() {
  window.history.pushState({}, "", "/devops");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function IntegrationHealthBanner() {
  const [items, setItems] = useState<IntegrationHealthItem[]>([]);
  const [resetting, setResetting] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const data = await Integrations.status();
        if (!cancelled) setItems(resolveVisibleIntegrations(data));
      } catch {
        // Silencioso a propósito: este banner es informativo, no una fuente
        // de error crítico — si /status no responde, simplemente no se muestra.
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, POLL_MS);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  if (!shouldRenderBanner(items)) return null;

  const handleRetry = async (item: IntegrationHealthItem) => {
    setResetting(item.key);
    try {
      await Integrations.reset(item.integration, item.project || null);
      const data = await Integrations.status();
      setItems(resolveVisibleIntegrations(data));
    } catch {
      // Si el reset falla, la tira sigue mostrando el item — el operador puede
      // reintentar; no hace falta un estado de error adicional aquí.
    } finally {
      setResetting(null);
    }
  };

  return (
    <div className={styles.wrap} role="status" aria-label="Estado de integraciones">
      {items.map((item) => (
        <div key={item.key} className={styles.row} role="alert">
          <span className={styles.icon} aria-hidden="true">⚠</span>
          <div className={styles.body}>
            <strong className={styles.title}>{item.title}</strong>
            {item.action ? <span className={styles.msg}>{item.action}</span> : null}
          </div>
          <div className={styles.actions}>
            {item.vault ? (
              <button className={styles.vaultBtn} onClick={goToVault}>
                Abrir Caja Fuerte
              </button>
            ) : null}
            <button
              className={styles.retryBtn}
              onClick={() => handleRetry(item)}
              disabled={resetting === item.key}
            >
              {resetting === item.key ? "Reintentando…" : "Reintentar ahora"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

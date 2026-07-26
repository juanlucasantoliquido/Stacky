import { useState } from "react";

import { DbCompare } from "../../api/endpoints";
import { Button } from "../ui";
import {
  canVerify,
  closureSummaryLabel,
  explainResult,
  sortForDisplay,
  type ClosureReport,
  type TriageSummary,
} from "./closureLogic";
import styles from "./GatesPanel.module.css";

/**
 * Plan 176 F7 — ¿Se aplicó lo que se confirmó, y sigue intacto lo que no?
 *
 * Después de ejecutar los scripts, mirar el diff "limpio" no alcanza: puede
 * estar limpio porque se ejecutó de más. Esto vuelve a comparar y contrasta el
 * resultado contra las decisiones que ya había tomado el operador.
 *
 * Lo importante es la segunda mitad: una diferencia EXCLUIDA que desapareció
 * significa que alguien tocó algo que se había decidido no tocar.
 */
export default function ClosurePanel({
  runId,
  runStatus,
  summary,
  enabled,
}: {
  runId: string;
  runStatus: string;
  summary: TriageSummary | null | undefined;
  enabled: boolean;
}) {
  const [reporte, setReporte] = useState<ClosureReport | null>(null);
  const [verificando, setVerificando] = useState(false);
  const [estado, setEstado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function verificar() {
    setVerificando(true);
    setError(null);
    setEstado("Comparando de nuevo…");
    try {
      await DbCompare.verifyClosure(runId);
      await esperarReporte();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo verificar la migración.");
      setEstado(null);
    } finally {
      setVerificando(false);
    }
  }

  /**
   * La verificación es una corrida completa: se sondea hasta que esté lista.
   * El 409 no es un error acá, es "todavía no": mostrarlo como error haría que
   * el operador reintente sobre algo que ya está andando.
   */
  async function esperarReporte() {
    const limite = Date.now() + 120_000;
    let espera = 500;
    while (Date.now() < limite) {
      try {
        const r = await DbCompare.getClosure(runId);
        setReporte(r as unknown as ClosureReport);
        setEstado(null);
        return;
      } catch {
        await new Promise((resolver) => setTimeout(resolver, espera));
        espera = Math.min(espera * 2, 5000);
      }
    }
    setEstado(null);
    setError("La verificación tardó demasiado. Volvé a consultarla en un rato.");
  }

  async function consultar() {
    setError(null);
    try {
      const r = await DbCompare.getClosure(runId);
      setReporte(r as unknown as ClosureReport);
    } catch {
      setError("Todavía no hay una verificación terminada para esta corrida.");
    }
  }

  if (!enabled) return null;

  const puede = canVerify(runStatus, summary);

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.headline}>
          Cierre de migración{reporte ? ` · ${closureSummaryLabel(reporte)}` : ""}
        </h3>
        <Button
          size="sm"
          variant="primary"
          onClick={verificar}
          disabled={!puede || verificando}
          title={
            puede
              ? undefined
              : "Necesitás una corrida terminada y al menos una decisión de triage."
          }
        >
          {verificando ? "Verificando…" : "Verificar migración"}
        </Button>
        {!reporte && !verificando && (
          <Button size="sm" onClick={consultar}>
            Ver última verificación
          </Button>
        )}
      </div>

      {estado && <p className={styles.detail}>{estado}</p>}
      {error && <p className={styles.detail}>{error}</p>}

      {reporte && reporte.results.length === 0 && (
        <p className={styles.empty}>
          No había decisiones que verificar en esta corrida.
        </p>
      )}

      {reporte && reporte.results.length > 0 && (
        <ul className={styles.list}>
          {sortForDisplay(reporte.results).map((r) => (
            <li
              key={r.item_key}
              className={`${styles.item} ${r.status === "violado" ? styles.itemFail : ""}`}
            >
              <strong>{r.item_key}</strong>
              <span className={styles.detail}>{explainResult(r)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

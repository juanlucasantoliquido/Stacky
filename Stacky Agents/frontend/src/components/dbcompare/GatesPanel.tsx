import { useMemo, useState } from "react";

import { DbCompare } from "../../api/endpoints";
import { Button } from "../ui";
import {
  canEvaluate,
  headlineFor,
  sortForDisplay,
  statusClass,
  statusLabel,
  statusOf,
  summarizeGates,
  type Gate,
  type GateResult,
} from "./gatesLogic";
import styles from "./GatesPanel.module.css";

/**
 * Plan 176 F4/F5 — Precondiciones antes de migrar.
 *
 * Poner un NOT NULL sobre una columna con NULLs, o crear una PK sobre datos
 * duplicados, hace fallar el ALTER a mitad de la migración. Estas consultas se
 * derivan del propio diff y se corren ANTES.
 *
 * Ejecutar es SIEMPRE un click: nada acá se dispara solo, y todo lo que corre
 * pasa por el guard de solo-lectura del backend.
 */
export default function GatesPanel({
  runId,
  runStatus,
  enabled,
}: {
  runId: string;
  runStatus: string;
  enabled: boolean;
}) {
  const [gates, setGates] = useState<Gate[] | null>(null);
  const [results, setResults] = useState<Record<string, GateResult>>({});
  const [cargando, setCargando] = useState(false);
  const [corriendo, setCorriendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resumen = useMemo(() => summarizeGates(gates, results), [gates, results]);
  const titular = headlineFor(gates, results);

  async function cargar() {
    setCargando(true);
    setError(null);
    try {
      const r = await DbCompare.getGates(runId);
      setGates((r.gates as Gate[]) ?? []);
      setResults((r.results as Record<string, GateResult>) ?? {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron leer las precondiciones.");
    } finally {
      setCargando(false);
    }
  }

  async function evaluar() {
    setCorriendo(true);
    setError(null);
    try {
      const r = await DbCompare.evaluateGates(runId);
      setResults((r.results as Record<string, GateResult>) ?? {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron verificar las precondiciones.");
    } finally {
      setCorriendo(false);
    }
  }

  if (!enabled) return null;

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <h3
          className={`${styles.headline} ${resumen.fail > 0 ? styles.headlineFail : ""}`}
        >
          Precondiciones · {titular}
        </h3>
        {gates === null ? (
          <Button size="sm" onClick={cargar} disabled={cargando}>
            {cargando ? "Cargando…" : "Ver precondiciones"}
          </Button>
        ) : (
          <>
            <Button
              size="sm"
              variant="primary"
              onClick={evaluar}
              disabled={corriendo || !canEvaluate(runStatus, enabled, gates)}
            >
              {corriendo ? "Verificando…" : "Verificar ahora"}
            </Button>
            <a href={DbCompare.gatesExportUrl(runId)} download>
              Descargar SQL
            </a>
          </>
        )}
      </div>

      {error && <p className={styles.detail}>{error}</p>}

      {gates !== null && gates.length === 0 && (
        <p className={styles.empty}>
          Ningún cambio de este diff requiere verificación previa.
        </p>
      )}

      {gates !== null && gates.length > 0 && (
        <ul className={styles.list}>
          {sortForDisplay(gates, results).map((g) => {
            const estado = statusOf(results, g.gate_id);
            const detalle = results[g.gate_id]?.detail;
            return (
              <li
                key={g.gate_id}
                className={`${styles.item} ${estado === "fail" ? styles.itemFail : ""}`}
              >
                <p className={styles.desc}>
                  <span className={`${styles.status} ${styles[statusClass(estado)]}`}>
                    {statusLabel(estado)}
                  </span>{" "}
                  · {g.description}
                </p>
                {detalle && <p className={styles.detail}>{detalle}</p>}
                <p className={styles.sql}>{g.sql}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

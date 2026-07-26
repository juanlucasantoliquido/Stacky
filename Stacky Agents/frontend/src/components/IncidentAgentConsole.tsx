import { useEffect, useState } from "react";

import { Executions, Incidents } from "../api/endpoints";
import {
  execLabel,
  logLineText,
  orderExecs,
  type IncidentExecRef,
} from "./incidentConsole";
import styles from "./IncidentResolverModal.module.css";

/**
 * Plan 200 F2 — "Consola del agente" dentro del detalle de la incidencia.
 *
 * Antes, para ver qué hizo el agente había que salir del detalle y buscar la
 * ejecución por id en otra pantalla — justo en el momento en que se está
 * decidiendo si publicar lo que produjo.
 *
 * No hay endpoint de transcript nuevo: se reusa `/api/executions/<id>/logs`, el
 * mismo que ya usa la consola de ejecuciones. Un canal más sería un canal más
 * que mantener.
 */
export function AgentConsole({ incidentId }: { incidentId: string }) {
  const [execs, setExecs] = useState<IncidentExecRef[] | null>(null);
  const [elegida, setElegida] = useState<number | null>(null);
  const [lineas, setLineas] = useState<string[] | null>(null);
  const [crudo, setCrudo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    Incidents.console(incidentId)
      .then((r) => {
        if (!vivo) return;
        const ordenadas = orderExecs(r.executions ?? []);
        setExecs(ordenadas);
        setElegida(ordenadas[0]?.execution_id ?? null);
      })
      // 404 = flag apagada o incidencia sin ejecuciones: no se renderiza nada.
      .catch(() => vivo && setExecs([]));
    return () => {
      vivo = false;
    };
  }, [incidentId]);

  useEffect(() => {
    if (elegida === null) return;
    let vivo = true;
    setError(null);
    setLineas(null);
    Executions.logsSnapshot(elegida)
      .then((eventos) => {
        if (!vivo) return;
        const lista = Array.isArray(eventos) ? eventos : [];
        // Un runtime que no emite eventos estructurados no puede quedar mudo:
        // se vuelca lo que haya y se dice que está crudo, en vez de mostrar una
        // consola vacía que parece "el agente no hizo nada".
        const estructurado = lista.some((e) => e && typeof e.message === "string");
        setCrudo(lista.length > 0 && !estructurado);
        setLineas(
          estructurado
            ? lista.map(logLineText).filter(Boolean)
            : lista.map((e) => (typeof e === "string" ? e : JSON.stringify(e))),
        );
      })
      .catch(() => vivo && setError("No se pudo leer el transcript de esta ejecución."));
    return () => {
      vivo = false;
    };
  }, [elegida]);

  if (!execs || execs.length === 0) return null;

  return (
    <details className={styles.previewSection}>
      <summary className={styles.previewHeader}>Consola del agente</summary>

      <div className={styles.label}>
        {execs.map((e) => (
          <button
            key={e.execution_id}
            type="button"
            className={e.execution_id === elegida ? styles.primaryBtn : styles.cancelBtn}
            onClick={() => setElegida(e.execution_id)}
          >
            {execLabel(e)}
          </button>
        ))}
      </div>

      {error && <p className={styles.errorMsg}>{error}</p>}
      {crudo && (
        <p className={styles.hint}>
          Transcript no estructurado para este runtime — mostrando log crudo
        </p>
      )}
      {lineas !== null && lineas.length === 0 && !error && (
        <p className={styles.hint}>Esta ejecución no dejó transcript.</p>
      )}
      {lineas !== null && lineas.length > 0 && (
        <pre className={styles.previewHtml}>{lineas.join("\n")}</pre>
      )}
    </details>
  );
}

export default AgentConsole;

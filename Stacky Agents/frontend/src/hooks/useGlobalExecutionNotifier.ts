import { useEffect, useRef } from "react";
import { Executions } from "../api/endpoints";
import { notifyExecutionFinished } from "../services/executionNotifier";
import { buildNotificationBody } from "../services/notifierCore";
import { clearOutcome, reportRunOutcome, setActiveRunCount } from "../services/tabTitle";
import { useActiveRunsGlobal } from "./useActiveRunsGlobal";

/**
 * U0.4 + plan 134 F2 — Notifica la finalización de CUALQUIER run de CUALQUIER
 * proyecto. Consume la query compartida del panel (running/preparing/queued,
 * all_projects) ⇒ también detecta muertes tempranas en preparing/queued y no
 * agrega NINGUNA request propia. Un id que desaparece del set se confirma con
 * Executions.byId (status final real) antes de notificar.
 */
export function useGlobalExecutionNotifier() {
  const activeQ = useActiveRunsGlobal();
  const prevActive = useRef<Set<number> | null>(null);

  useEffect(() => {
    if (activeQ.data == null) return; // sin snapshot (carga o error): no comparar
    const current = new Set<number>(activeQ.data.map((e) => e.id));
    const prev = prevActive.current;
    prevActive.current = current;
    if (prev == null) return; // primer snapshot: nada contra qué comparar

    for (const prevId of prev) {
      if (!current.has(prevId)) {
        void Executions.byId(prevId)
          .then((row) => {
            notifyExecutionFinished({
              execution_id: row.id,
              agent_type: String(row.agent_type || "agente"),
              status:
                (row.status as "completed" | "error" | "cancelled" | "needs_review") ||
                "completed",
              ticket_label: buildNotificationBody(row),
            });
            reportRunOutcome(String(row.status || "completed"));
          })
          .catch(() => {});
      }
    }
  }, [activeQ.data]);

  // F3 — el título refleja el conteo real de runs activos.
  useEffect(() => {
    if (activeQ.data != null) setActiveRunCount(activeQ.data.length);
  }, [activeQ.data]);

  // F3 — mirar la pestaña (foco, visibilidad o click) limpia el ✅/❌ persistente.
  useEffect(() => {
    const clear = () => clearOutcome();
    const onVisibility = () => {
      if (document.visibilityState === "visible") clearOutcome();
    };
    window.addEventListener("focus", clear);
    window.addEventListener("pointerdown", clear);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", clear);
      window.removeEventListener("pointerdown", clear);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);
}

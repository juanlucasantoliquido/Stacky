import { useEffect, useRef } from "react";
import { Executions } from "../api/endpoints";
import { buildNotificationBody } from "../services/notifierCore";
import { publishActivity, getActivitySnapshot } from "../services/activityCenter";
import { severityFromRunStatus } from "../services/activityReducer";
import { diffFinishedIds } from "../services/runCapture";
import { useActiveRunsGlobal } from "./useActiveRunsGlobal";

/**
 * Plan 152 F2 — Puebla la categoría `run` del Centro de Actividad reusando la
 * MISMA query compartida que el panel y el notificador global (0 requests
 * propios de refresco). Un id que desaparece del set activo se confirma con
 * Executions.byId (status final real) y se publica al store.
 *
 * C2: con enabled=false NO corre nada (ni comparación, ni byId, ni storage).
 * No edita useGlobalExecutionNotifier.ts: replica el patrón del diff en local.
 */
export function useRunActivityCapture(enabled: boolean): void {
  const activeQ = useActiveRunsGlobal();
  const prev = useRef<Set<number> | null>(null);

  useEffect(() => {
    if (!enabled) return; // C2: flag OFF ⇒ cero trabajo
    if (activeQ.data == null) return; // sin snapshot (carga/error): no comparar
    const current = new Set<number>(activeQ.data.map((e) => e.id));
    const finished = diffFinishedIds(prev.current, current);
    prev.current = current; // primer snapshot: prev era null ⇒ diff = [] (sin falsos positivos)
    for (const id of finished) {
      const key = `run:${id}`;
      // Doble-emisión con el notificador de 134 es inofensiva (dedup por key en
      // el store); además si el evento ya está, no reconsultamos el detalle.
      if (getActivitySnapshot().events.some((e) => e.key === key)) continue;
      void Executions.byId(id)
        .then((row) => {
          const status = String(row.status || "completed");
          publishActivity({
            key,
            kind: "run",
            severity: severityFromRunStatus(status),
            title: `Agente ${row.agent_type || "agente"} — ${status}`,
            body: buildNotificationBody(row),
            ts: Date.now(),
            nav: { tab: "team", executionId: row.id },
          });
        })
        .catch(() => {
          /* el detalle falló: se ignora, no se inventa evento */
        });
    }
  }, [activeQ.data, enabled]);
}

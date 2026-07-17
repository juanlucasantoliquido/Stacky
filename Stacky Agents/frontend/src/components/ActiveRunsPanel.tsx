import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Move, Terminal, X } from "lucide-react";

import { Executions } from "../api/endpoints";
import useLocalStorageState from "../hooks/useLocalStorageState";
import { useActiveRunsGlobal } from "../hooks/useActiveRunsGlobal";
import { formatLoadErrorMessage } from "../utils/loadError";
import { useWorkbench } from "../store/workbench";
import styles from "./ActiveRunsPanel.module.css";

/**
 * Esquinas de pantalla entre las que se puede mover el panel (Plan operador
 * 2026-07-09: el panel tapaba botones al quedar fijo arriba-a-la-derecha sin
 * forma de correrlo). Ciclamos en sentido horario con el botón "mover".
 */
const CORNERS = ["top-right", "bottom-right", "bottom-left", "top-left"] as const;
type Corner = (typeof CORNERS)[number];

const CORNER_CLASS: Record<Corner, string> = {
  "top-right": styles.posTopRight,
  "bottom-right": styles.posBottomRight,
  "bottom-left": styles.posBottomLeft,
  "top-left": styles.posTopLeft,
};

function nextCorner(current: Corner): Corner {
  const idx = CORNERS.indexOf(current);
  return CORNERS[(idx + 1) % CORNERS.length];
}

export default function ActiveRunsPanel() {
  const qc = useQueryClient();

  // Abrir la consola en vivo de un run reusa el mecanismo único y ya existente
  // del repo: setCodexConsoleExecution del store (mismo patrón que
  // pages/TicketBoard.tsx:308). CodexConsoleDock ya está montado globalmente
  // en App.tsx, así que con setear el id alcanza — no se crea nada nuevo.
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const consoleExecutionId = useWorkbench((s) => s.codexConsoleExecutionId);

  // Colapsado y posición persisten en localStorage (mismo patrón que el resto
  // de las preferencias de UI del proyecto — ver useLocalStorageState) para
  // que sobrevivan a un F5 sin que el operador tenga que reconfigurar nada.
  const [collapsed, setCollapsed] = useLocalStorageState<boolean>(
    "stacky.activeRunsPanel.collapsed",
    false
  );
  const [corner, setCorner] = useLocalStorageState<Corner>(
    "stacky.activeRunsPanel.corner",
    "top-right"
  );

  const { data, isError: fetchFailed, dataUpdatedAt } = useActiveRunsGlobal();

  const cancelMutation = useMutation({
    mutationFn: (id: number) => Executions.cancel(id),
    onSettled: () => {
      // Refrescar todo lo que depende del estado de runs activos.
      qc.invalidateQueries({ queryKey: ["executions"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
    },
  });

  const runs = data ?? [];
  if (runs.length === 0) return null;

  const cornerClass = CORNER_CLASS[corner] ?? styles.posTopRight;

  // Colapsado: solo un indicador mínimo (persiste posición) — el panel sigue
  // "vivo" en el sentido de que este badge refleja el conteo en tiempo real,
  // así el operador nunca pierde de vista si hay runs activos.
  if (collapsed) {
    return (
      <button
        type="button"
        className={`${styles.miniBadge} ${cornerClass}`}
        onClick={() => setCollapsed(false)}
        title="Mostrar ejecuciones activas"
        aria-label={`Mostrar ejecuciones activas (${runs.length})`}
      >
        <span className={styles.dot} aria-hidden />
        {runs.length}
      </button>
    );
  }

  return (
    <div className={`${styles.panel} ${cornerClass}`} role="region" aria-label="Ejecuciones activas">
      <div className={styles.head}>
        EJECUCIONES ACTIVAS <span className={styles.count}>{runs.length}</span>
        <div className={styles.headActions}>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setCorner(nextCorner(corner))}
            title="Mover panel a otra esquina"
            aria-label="Mover panel a otra esquina"
          >
            <Move size={13} />
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => setCollapsed(true)}
            title="Ocultar panel (queda un indicador visible)"
            aria-label="Ocultar panel"
          >
            <X size={13} />
          </button>
        </div>
      </div>
      <ul className={styles.list}>
        {runs.map((e) => {
          const cancelling =
            cancelMutation.isPending && cancelMutation.variables === e.id;
          return (
            <li key={e.id} className={styles.item}>
              <span className={styles.dot} aria-hidden />
              <span className={styles.id}>#{e.id}</span>
              <span
                className={styles.meta}
                title={`${e.project ?? "proyecto ?"} · ticket ${e.ticket_id}${e.ticket_title ? ` · ${e.ticket_title}` : ""} · ${e.agent_type} · ${e.status}`}
              >
                {e.project ? `${e.project} · ` : ""}
                {e.ticket_title ?? `ticket ${e.ticket_id}`} · {e.agent_type} · {e.status}
              </span>
              <button
                type="button"
                className={styles.consoleBtn}
                title={`Ver consola en vivo de la ejecución #${e.id}`}
                aria-label={`Ver consola de la ejecución #${e.id}`}
                aria-pressed={consoleExecutionId === e.id}
                onClick={() =>
                  setCodexConsoleExecution(
                    consoleExecutionId === e.id ? null : e.id,
                    false,
                  )
                }
              >
                <Terminal size={13} aria-hidden />
              </button>
              <button
                type="button"
                className={styles.cancelBtn}
                disabled={cancelling}
                title="Cancelar esta ejecución (detiene la sesión del agente)"
                onClick={() => {
                  if (cancelling) return;
                  if (
                    window.confirm(
                      `¿Cancelar la ejecución #${e.id}? ${e.project ? `[${e.project}] ` : ""}${e.ticket_title ?? `ticket ${e.ticket_id}`} · ${e.agent_type}. Se detendrá la sesión del agente.`
                    )
                  ) {
                    cancelMutation.mutate(e.id);
                  }
                }}
              >
                {cancelling ? "cancelando…" : "✕ Cancelar"}
              </button>
            </li>
          );
        })}
      </ul>
      {fetchFailed && (
        <div className={styles.staleNotice} role="status">
          {/* [ADICIÓN ARQUITECTO 2] hora del último dato bueno, directo del
              UseQueryResult del contrato 134 — cero mecanismos nuevos. */}
          Sin conexión con el backend — mostrando el último estado conocido
          {dataUpdatedAt > 0 ? ` (${new Date(dataUpdatedAt).toLocaleTimeString()})` : ""}.
        </div>
      )}
      {cancelMutation.isError && (
        <div className={styles.cancelError} role="alert">
          <span className={styles.cancelErrorText}>
            No se pudo cancelar #{cancelMutation.variables}:{" "}
            {formatLoadErrorMessage(cancelMutation.error)}
          </span>
          <button
            type="button"
            className={styles.cancelRetry}
            onClick={() => cancelMutation.mutate(cancelMutation.variables as number)}
          >
            Reintentar
          </button>
          <button
            type="button"
            className={styles.cancelDismiss}
            aria-label="Descartar aviso de cancelación"
            onClick={() => cancelMutation.reset()}
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

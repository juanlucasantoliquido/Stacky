/**
 * UnblockerPage — "Desatascador de tickets".
 *
 * Vista agregada de todos los tickets que el copilot está trabajando (en
 * ejecución) o que dejaron artifacts listos en disco. Cada refresco vuelve a
 * detectar la readiness (comment.html / pending-task.json + plan) para que el
 * operador pueda destrabar el flujo manualmente sin frenar al dev:
 *
 *   - "Crear Task(s) en ADO"      → reusa CreateChildTaskButton (epics pendientes)
 *   - "Generar comentario en ADO" → reusa FinishWorkButton (tickets con comment.html)
 *
 * Datos: GET /api/tickets/unblocker-board (Tickets.unblockerBoard).
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Tickets,
  type UnblockerItem,
  type UnblockerReadiness,
} from "../api/endpoints";
import type { Ticket } from "../types";
import { useWorkbench } from "../store/workbench";
import FinishWorkButton from "../components/FinishWorkButton";
import CreateChildTaskButton from "../components/CreateChildTaskButton";
import styles from "./UnblockerPage.module.css";

const READINESS_LABEL: Record<UnblockerReadiness, string> = {
  task_ready: "Task lista para crear",
  comment_ready: "Comentario listo para publicar",
  waiting_files: "Esperando archivos del agente",
  artifacts_idle: "Artifacts en disco",
  files_error: "⚠️ pending-task.json malformado",
};

const READINESS_CLASS: Record<UnblockerReadiness, string> = {
  task_ready: styles.badgeTask,
  comment_ready: styles.badgeComment,
  waiting_files: styles.badgeWaiting,
  artifacts_idle: styles.badgeIdle,
  files_error: styles.badgeError,
};

function UnblockerCard({
  item,
  onChanged,
}: {
  item: UnblockerItem;
  onChanged: () => void;
}) {
  // Ticket mínimo para FinishWorkButton (sólo usa id / ado_id / title).
  const ticketShim: Ticket = {
    id: item.ticket_id,
    ado_id: item.ado_id ?? 0,
    project: "",
    title: item.title,
    ado_state: item.ado_state ?? undefined,
    ado_url: item.ado_url ?? undefined,
    work_item_type: item.work_item_type ?? undefined,
    stacky_status: (item.stacky_status as Ticket["stacky_status"]) ?? undefined,
  };

  const isEpicWithPending = item.total_pending > 0 && item.ado_id != null;
  const canPublishComment = item.comment.exists && item.ado_id != null;

  return (
    <article className={styles.card} data-readiness={item.readiness}>
      <header className={styles.cardHeader}>
        <div className={styles.titleRow}>
          {item.ado_url ? (
            <a
              href={item.ado_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.adoTag}
            >
              ADO-{item.ado_id}
            </a>
          ) : (
            <span className={styles.adoTag}>#{item.ticket_id}</span>
          )}
          {item.work_item_type && (
            <span className={styles.typeTag}>{item.work_item_type}</span>
          )}
          {item.running && <span className={styles.runningDot} title="En ejecución">● en ejecución</span>}
        </div>
        <span className={`${styles.badge} ${READINESS_CLASS[item.readiness]}`}>
          {READINESS_LABEL[item.readiness]}
        </span>
      </header>

      <h3 className={styles.cardTitle} title={item.title}>{item.title}</h3>

      <div className={styles.meta}>
        <span>Estado ADO: <strong>{item.ado_state ?? "—"}</strong></span>
        <span>Stacky: <strong>{item.stacky_status}</strong></span>
        {item.last_execution && (
          <span>
            Último agente: <strong>{item.last_execution.agent_type ?? "—"}</strong>{" "}
            ({item.last_execution.status})
          </span>
        )}
      </div>

      {/* Readiness de archivos */}
      <ul className={styles.fileList}>
        <li className={item.comment.exists ? styles.fileOk : styles.fileMissing}>
          comment.html{" "}
          {item.comment.exists
            ? `✓ (${(item.comment.size_bytes / 1024).toFixed(1)} KB)`
            : "— no encontrado"}
        </li>
        <li className={item.total_pending > 0 ? styles.fileOk : styles.fileMissing}>
          pending-task.json{" "}
          {item.total_pending > 0
            ? `✓ ${item.total_pending} pendiente(s)${
                item.total_consumed ? `, ${item.total_consumed} ya creada(s)` : ""
              }`
            : item.total_consumed
            ? `— ${item.total_consumed} ya creada(s)`
            : "— ninguno"}
        </li>
      </ul>

      {item.pending_tasks.length > 0 && (
        <ul className={styles.rfList}>
          {item.pending_tasks.map((pt) => (
            <li key={pt.rf_id}>
              <strong>{pt.rf_id}</strong> — {pt.title}{" "}
              {pt.plan_exists ? (
                <span className={styles.planOk}>plan ✓</span>
              ) : (
                <span className={styles.planMissing}>plan ✗</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {item.blockers.length > 0 && (
        <ul className={styles.blockers}>
          {item.blockers.map((b, i) => (
            <li key={i}>⚠ {b}</li>
          ))}
        </ul>
      )}

      {/* Acciones de desatasco */}
      <div className={styles.actions} onClick={(e) => e.stopPropagation()}>
        {isEpicWithPending && (
          <CreateChildTaskButton
            epicAdoId={item.ado_id as number}
            onTaskCreated={onChanged}
          />
        )}
        {canPublishComment && (
          <FinishWorkButton ticket={ticketShim} onCompleted={onChanged} />
        )}
        {!isEpicWithPending && !canPublishComment && (
          <span className={styles.noAction}>
            Sin archivos listos todavía — refrescar cuando el agente termine.
          </span>
        )}
      </div>
    </article>
  );
}

export default function UnblockerPage() {
  const qc = useQueryClient();
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["unblocker-board", activeProjectName],
    queryFn: () => Tickets.unblockerBoard(activeProjectName),
    refetchOnWindowFocus: false,
  });

  const handleChanged = useCallback(() => {
    refetch();
    qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
    qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
  }, [refetch, qc, activeProjectName]);

  const items = data?.items ?? [];
  const counts = data?.counts;

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h2 className={styles.h2}>🧹 Desatascador de tickets</h2>
          <p className={styles.sub}>
            Stacky detecta y crea las Tasks / publica los comentarios
            automáticamente cuando el agente termina. Esta vista es el{" "}
            <strong>fallback puntual</strong>: si algo no se autogeneró, destrabá
            el flujo a mano con los archivos ya producidos — sin frenar al dev.
          </p>
        </div>
        <button
          className={styles.refreshBtn}
          onClick={() => refetch()}
          disabled={isFetching}
        >
          {isFetching ? "Refrescando…" : "↻ Refrescar"}
        </button>
      </header>

      {counts && (
        <div className={styles.counts}>
          <span className={styles.countTask}>{counts.task_ready} task(s) listas</span>
          <span className={styles.countComment}>{counts.comment_ready} comentario(s) listos</span>
          {counts.files_error > 0 && (
            <span className={styles.countError}>{counts.files_error} malformado(s)</span>
          )}
          <span className={styles.countWaiting}>{counts.waiting_files} esperando</span>
          <span className={styles.countRunning}>{counts.running} en ejecución</span>
        </div>
      )}

      {isLoading && <p className={styles.state}>Cargando…</p>}
      {isError && (
        <p className={styles.stateError}>
          Error al cargar el board: {(error as Error)?.message ?? "desconocido"}
        </p>
      )}
      {!isLoading && !isError && items.length === 0 && (
        <p className={styles.state}>
          No hay tickets en ejecución ni artifacts pendientes. Todo destrabado. 🎉
        </p>
      )}

      <div className={styles.grid}>
        {items.map((item) => (
          <UnblockerCard key={item.ticket_id} item={item} onChanged={handleChanged} />
        ))}
      </div>
    </div>
  );
}

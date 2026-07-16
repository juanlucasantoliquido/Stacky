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
import { useCallback, useState, type DragEvent, type ChangeEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Tickets,
  type UnblockerItem,
  type UnblockerReadiness,
} from "../api/endpoints";
import type { Ticket } from "../types";
import { useWorkbench } from "../store/workbench";
import FinishWorkButton from "../components/FinishWorkButton";
import styles from "./UnblockerPage.module.css";
import { getWorkItemTypeColor } from "../utils/workItemTypeColor";

const READINESS_LABEL: Record<UnblockerReadiness, string> = {
  task_ready: "Task lista para crear",
  stale_consumed: "⚠️ Task borrada en ADO — recrear",
  comment_ready: "Comentario listo para publicar",
  waiting_files: "Esperando archivos del agente",
  artifacts_idle: "Artifacts en disco",
  files_error: "⚠️ pending-task.json malformado",
  completed_ok: "Completado",   // Plan 66
};

const READINESS_CLASS: Record<UnblockerReadiness, string> = {
  task_ready: styles.badgeTask,
  stale_consumed: styles.badgeError,
  comment_ready: styles.badgeComment,
  waiting_files: styles.badgeWaiting,
  artifacts_idle: styles.badgeIdle,
  files_error: styles.badgeError,
  completed_ok: styles.badgeCompleted,   // Plan 66
};

function UnblockerCard({
  item,
  onChanged,
  artifactRoot,
  activeProjectName,
}: {
  item: UnblockerItem;
  onChanged: () => void;
  artifactRoot: string | null;
  activeProjectName: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [dropActive, setDropActive] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

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

  // Compat: backend viejo no manda stale_consumed.
  const staleConsumed = item.stale_consumed ?? [];
  const isEpicWithPending = item.total_pending > 0 && item.ado_id != null;
  const hasStaleConsumed = staleConsumed.length > 0 && item.ado_id != null;
  const canPublishComment = item.comment.exists && item.ado_id != null;

  const createDetectedTasks = useCallback(async () => {
    if (!item.ado_id || item.pending_tasks.length === 0) return;
    setBusy(true);
    setActionMessage("Creando Task(s) detectadas...");
    try {
      for (const pt of item.pending_tasks) {
        const result = await Tickets.createChildTask(item.ado_id, {
          pending_task_path: pt.pending_task_path,
          operator_reason: "Desatascador: creación manual desde artifact detectado",
          project: activeProjectName,
          repo_root: artifactRoot,
        });
        if (!result.ok) {
          throw new Error(result.message || result.error || "create-child-task falló");
        }
      }
      setActionMessage("Task(s) creadas.");
      onChanged();
    } catch (err) {
      setActionMessage((err as Error)?.message ?? "No se pudo crear la Task.");
    } finally {
      setBusy(false);
    }
  }, [item.ado_id, item.pending_tasks, activeProjectName, artifactRoot, onChanged]);

  // Fix ADO-241: el archivo quedó "consumed" apuntando a una Task que ya no
  // existe en ADO. create-child-task verifica contra ADO, resetea el marker
  // stale y crea la Task de nuevo (si la Task siguiera viva, responde
  // idempotente sin duplicar).
  const recreateStaleTasks = useCallback(async () => {
    if (!item.ado_id || staleConsumed.length === 0) return;
    setBusy(true);
    setActionMessage("Recreando Task(s) borrada(s) en ADO...");
    try {
      for (const st of staleConsumed) {
        const result = await Tickets.createChildTask(item.ado_id, {
          pending_task_path: st.pending_task_path,
          operator_reason:
            `Desatascador: recreación — la Task ADO-${st.task_ado_id} fue borrada en ADO`,
          project: activeProjectName,
          repo_root: artifactRoot,
        });
        if (!result.ok) {
          throw new Error(result.message || result.error || "create-child-task falló");
        }
        setActionMessage(`Task recreada: ADO-${result.task_ado_id}`);
      }
      onChanged();
    } catch (err) {
      setActionMessage((err as Error)?.message ?? "No se pudo recrear la Task.");
    } finally {
      setBusy(false);
    }
  }, [item.ado_id, staleConsumed, activeProjectName, artifactRoot, onChanged]);

  // Plan 66 F2 — helper compartido entre handleDrop y handleFileSelect
  const _processFiles = useCallback(async (rawFiles: File[]) => {
    if (!item.ado_id || rawFiles.length === 0) return;
    setBusy(true);
    setActionMessage("Leyendo archivo(s)...");
    try {
      const files = await Promise.all(
        rawFiles.map(async (file) => ({
          name: file.name,
          content: await file.text(),
        }))
      );
      const hasPending = files.some((f) => f.name.toLowerCase() === "pending-task.json");
      const hasComment = files.some((f) => f.name.toLowerCase().endsWith(".html"));
      const rescueRoot = hasComment && !hasPending ? null : artifactRoot;
      const rescue = await Tickets.rescueArtifact(item.ado_id, {
        artifact_type: "auto",
        files,
        project: activeProjectName,
        repo_root: rescueRoot,
      });
      if (!rescue.ok) {
        throw new Error(rescue.message || rescue.error || "No se pudo preparar el artifact.");
      }
      if (rescue.artifact_type === "pending_task" && rescue.pending_task_path) {
        setActionMessage("Artifact preparado. Creando Task...");
        const created = await Tickets.createChildTask(item.ado_id, {
          pending_task_path: rescue.pending_task_path,
          operator_reason: "Desatascador: creación desde archivo subido",
          project: activeProjectName,
          repo_root: rescue.repo_root || rescueRoot,
        });
        if (!created.ok) {
          throw new Error(created.message || created.error || "create-child-task falló");
        }
        setActionMessage(`Task creada: ADO-${created.task_ado_id}`);
      } else if (rescue.artifact_type === "comment" && rescue.html_output_path) {
        setActionMessage("Comentario preparado. Publicando...");
        const published = await Tickets.finishWork(item.ticket_id, {
          operator_reason: "Desatascador: publicación desde comment.html subido",
          publish_to_ado: true,
          html_output_path: rescue.html_output_path,
          force_publish: true,
          force_finish: true,
          cancel_active_execution: true,
        });
        if (!published.ok) {
          throw new Error("finish-work no pudo completar la publicación.");
        }
        setActionMessage("Comentario publicado.");
      } else {
        throw new Error("El backend no reconoció pending-task.json ni comment.html.");
      }
      onChanged();
    } catch (err) {
      setActionMessage((err as Error)?.message ?? "No se pudo procesar el archivo.");
    } finally {
      setBusy(false);
    }
  }, [item.ado_id, item.ticket_id, activeProjectName, artifactRoot, onChanged]);

  const handleDrop = useCallback(async (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDropActive(false);
    await _processFiles(Array.from(event.dataTransfer.files || []));
  }, [_processFiles]);

  // Plan 66 F2 — file picker como alternativa al drag-and-drop
  const handleFileSelect = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const selected = Array.from(event.target.files || []);
      event.target.value = "";  // reset para permitir re-selección del mismo archivo
      await _processFiles(selected);
    },
    [_processFiles]
  );

  // Plan 149 F5 — re-intake 1-click de un pending-task.json en cuarentena
  // (human-in-the-loop: el operador lo dispara desde el board, nunca automático).
  const reprocessPendingTask = useCallback(async (pendingTaskPath: string) => {
    if (!item.ado_id) return;
    setBusy(true);
    setActionMessage("Re-procesando pending-task.json...");
    try {
      const result = await Tickets.reintakePendingTask({
        pending_task_path: pendingTaskPath,
        epic_ado_id: item.ado_id,
        project: activeProjectName,
      });
      if (!result.ok) {
        const reason =
          result.details?.errors?.join("; ") || result.message || result.error ||
          "el archivo sigue inválido";
        throw new Error(reason);
      }
      // C7 — un 200 con create_child_task.ok=false es un fallo lógico blando
      // (idempotente-consumed, etc.): surfacearlo igual, nunca asumir éxito
      // solo por el status HTTP.
      const cct = result.create_child_task as
        | { ok?: boolean; message?: string; error?: string; task_ado_id?: number }
        | undefined;
      if (cct && cct.ok === false) {
        throw new Error(cct.message || cct.error || "create-child-task no pudo completar la Task.");
      }
      setActionMessage(
        cct?.task_ado_id ? `Task creada: ADO-${cct.task_ado_id}` : "Re-procesado correctamente."
      );
      onChanged();
    } catch (err) {
      setActionMessage((err as Error)?.message ?? "No se pudo re-procesar el archivo.");
    } finally {
      setBusy(false);
    }
  }, [item.ado_id, activeProjectName, onChanged]);

  return (
    <article
      className={`${styles.card} ${dropActive ? styles.cardDropActive : ""}`}
      data-readiness={item.readiness}
      onDragOver={(e) => {
        e.preventDefault();
        setDropActive(true);
      }}
      onDragLeave={() => setDropActive(false)}
      onDrop={handleDrop}
    >
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
            <span
              className={styles.typeTag}
              style={{ color: getWorkItemTypeColor(item.work_item_type) }}
            >
              {item.work_item_type}
            </span>
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
            <li key={`${pt.rf_id}-${pt.pending_task_path}`}>
              <strong>{pt.rf_id}</strong> — {pt.title}{" "}
              {pt.plan_exists ? (
                <span className={styles.planOk}>plan ✓</span>
              ) : (
                <span className={styles.planMissing}>plan ✗</span>
              )}
              <code className={styles.pathCode}>{pt.pending_task_path}</code>
            </li>
          ))}
        </ul>
      )}

      {staleConsumed.length > 0 && (
        <ul className={styles.rfList}>
          {staleConsumed.map((st) => (
            <li key={`stale-${st.rf_id}-${st.pending_task_path}`}>
              <strong>{st.rf_id}</strong> — {st.title}{" "}
              <span className={styles.planMissing}>
                Task ADO-{st.task_ado_id ?? "?"} borrada en ADO
              </span>
              <code className={styles.pathCode}>{st.pending_task_path}</code>
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

      {/* Plan 149 F4/F5 — pending-task.json rechazados por intake, con causa
          exacta (reason_code) y botón de re-procesamiento 1-click. */}
      {item.parse_errors.length > 0 && (
        <ul className={styles.blockers}>
          {item.parse_errors.map((pe) => (
            <li key={`pe-${pe.rf_id}-${pe.pending_task_path}`}>
              ⚠ {pe.rf_id}: {pe.error}
              {pe.reason_code && (
                <code className={styles.pathCode}> [{pe.reason_code}]</code>
              )}
              {" "}
              <button
                className={styles.actionBtn}
                onClick={() => reprocessPendingTask(pe.pending_task_path)}
                disabled={busy}
              >
                {busy ? "Procesando..." : "Re-procesar"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Acciones de desatasco */}
      <div className={styles.actions} onClick={(e) => e.stopPropagation()}>
        {isEpicWithPending && (
          <button className={styles.actionBtn} onClick={createDetectedTasks} disabled={busy}>
            {busy ? "Procesando..." : "Crear Task(s) detectadas"}
          </button>
        )}
        {hasStaleConsumed && (
          <button className={styles.actionBtn} onClick={recreateStaleTasks} disabled={busy}>
            {busy ? "Procesando..." : "Recrear Task borrada en ADO"}
          </button>
        )}
        {canPublishComment && (
          <FinishWorkButton ticket={ticketShim} onCompleted={onChanged} />
        )}
        {!isEpicWithPending && !hasStaleConsumed && !canPublishComment && (
          <span className={styles.noAction}>
            Sin archivos listos todavía — refrescar cuando el agente termine.
          </span>
        )}
      </div>
      <div className={styles.dropZone}>
        Arrastrá pending-task.json, plan-de-pruebas.md o comment.html para rescatar este ADO.
        {/* Plan 66 F2 — alternativa sin drag: selector de archivos */}
        <label className={styles.filePicker}>
          <span>o seleccionar archivo</span>
          <input
            type="file"
            multiple
            style={{ display: "none" }}
            onChange={handleFileSelect}
            disabled={busy}
          />
        </label>
      </div>
      {actionMessage && <p className={styles.actionMessage}>{actionMessage}</p>}
    </article>
  );
}

export default function UnblockerPage() {
  const qc = useQueryClient();
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const [rootDraft, setRootDraft] = useState("");
  const [artifactRoot, setArtifactRoot] = useState<string | null>(null);
  // Plan 66 F2 — toggle para mostrar/ocultar tickets completados (default: mostrar)
  const [includeCompleted, setIncludeCompleted] = useState(true);

  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["unblocker-board", activeProjectName, artifactRoot, includeCompleted],
    queryFn: () => Tickets.unblockerBoard(activeProjectName, artifactRoot, includeCompleted),
    refetchOnWindowFocus: false,
  });

  const handleChanged = useCallback(() => {
    refetch();
    qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
    qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
  }, [refetch, qc, activeProjectName]);

  const items = data?.items ?? [];
  const counts = data?.counts;
  const scan = data?.scan;

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
        {/* Plan 66 F2 — toggle completados */}
        <button
          className={`${styles.refreshBtn} ${includeCompleted ? styles.toggleActive : ""}`}
          onClick={() => setIncludeCompleted((v) => !v)}
        >
          {includeCompleted ? "Ocultar completados" : "Mostrar completados"}
        </button>
      </header>

      <form
        className={styles.pathBar}
        onSubmit={(event) => {
          event.preventDefault();
          setArtifactRoot(rootDraft.trim() || null);
        }}
      >
        <label>
          Ruta de artifacts
          <input
            value={rootDraft}
            onChange={(event) => setRootDraft(event.target.value)}
            placeholder={scan?.outputs_dir || "N:\\GIT\\RS\\RSPACIFICO o ...\\Agentes\\outputs"}
          />
        </label>
        <button className={styles.refreshBtn} type="submit">Aplicar ruta</button>
        <button
          className={styles.refreshBtn}
          type="button"
          onClick={() => {
            setRootDraft("");
            setArtifactRoot(null);
          }}
        >
          Usar actual
        </button>
      </form>

      {scan && (
        <div className={styles.scanInfo}>
          <div><strong>Desatascador lee:</strong> <code>{scan.outputs_dir}</code> ({scan.outputs_dir_exists ? "existe" : "no existe"})</div>
          <div><strong>Repo root:</strong> <code>{scan.repo_root}</code></div>
          {scan.watcher && (
            <div>
              <strong>Watcher runtime:</strong>{" "}
              <code>{scan.watcher.outputs_dir ?? "no iniciado"}</code>{" "}
              {scan.watcher.running ? "(corriendo)" : "(detenido/ad-hoc)"}
            </div>
          )}
          <div className={styles.scanRoots}>
            {scan.roots.map((root) => (
              <span key={root.path} className={root.exists ? styles.rootOk : styles.rootMissing}>
                {root.label}: {root.exists ? "ok" : "no existe"}
              </span>
            ))}
          </div>
        </div>
      )}

      {counts && (
        <div className={styles.counts}>
          <span className={styles.countTask}>{counts.task_ready} task(s) listas</span>
          <span className={styles.countComment}>{counts.comment_ready} comentario(s) listos</span>
          {(counts.stale_consumed ?? 0) > 0 && (
            <span className={styles.countError}>
              {counts.stale_consumed} task(s) borrada(s) en ADO
            </span>
          )}
          {counts.files_error > 0 && (
            <span className={styles.countError}>{counts.files_error} malformado(s)</span>
          )}
          <span className={styles.countWaiting}>{counts.waiting_files} esperando</span>
          <span className={styles.countRunning}>{counts.running} en ejecución</span>
          {/* Plan 66 F2 — completed_ok (solo si hay) */}
          {(counts.completed_ok ?? 0) > 0 && (
            <span className={styles.countCompleted}>
              {counts.completed_ok} completado(s)
              {(counts.completed_ok_truncated ?? 0) > 0 && (
                <> (+{counts.completed_ok_truncated} ocultados por cap)</>
              )}
            </span>
          )}
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
          <UnblockerCard
            key={item.ticket_id}
            item={item}
            onChanged={handleChanged}
            artifactRoot={artifactRoot}
            activeProjectName={activeProjectName}
          />
        ))}
      </div>
    </div>
  );
}

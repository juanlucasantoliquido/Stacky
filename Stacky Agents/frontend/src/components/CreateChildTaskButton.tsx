/**
 * CreateChildTaskButton — Crear Tasks hijas en ADO desde pending-task.json (Fase 2).
 *
 * Visible en el card de un Epic cuando hay pending-task.json pendientes en
 * Agentes/outputs/epic-{ado_id}/.
 *
 * Flujo:
 *   1. Fetch de GET /api/tickets/by-ado/{epicAdoId}/pending-tasks al montar.
 *   2. Si total_pending=0 → no se renderiza el botón.
 *   3. Click → modal con lista de RFs pendientes.
 *   4. Operador selecciona RFs, escribe motivo, confirma.
 *   5. Por cada RF seleccionado → POST /api/tickets/by-ado/{epicAdoId}/create-child-task.
 *   6. Muestra resultado por RF (ok / parcial / error).
 *   7. Toast final con resumen. Invalida queries de tickets/hierarchy.
 *
 * Diseño: sigue el patrón de FinishWorkButton (modal, A11y, sin librerías UI extra).
 */
import { useState, useCallback, useEffect, useId } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Tickets,
  type PendingTaskItem,
  type CreateChildTaskResponse,
} from "../api/endpoints";
import styles from "./CreateChildTaskButton.module.css";

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  epicAdoId: number;
  /** Deshabilitado externamente (ej: operación en curso). */
  disabled?: boolean;
  /** Callback al crear al menos una Task exitosamente. */
  onTaskCreated?: () => void;
}

// ─── Resultado por RF ─────────────────────────────────────────────────────────

interface RfResult {
  rf_id: string;
  title: string;
  status: "pending" | "running" | "ok" | "partial" | "error" | "idempotent";
  response?: CreateChildTaskResponse;
  error?: string;
}

// ─── Componente ───────────────────────────────────────────────────────────────

export default function CreateChildTaskButton({
  epicAdoId,
  disabled,
  onTaskCreated,
}: Props) {
  const qc = useQueryClient();
  const modalId = useId();

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [rfResults, setRfResults] = useState<RfResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; message: string } | null>(null);

  // ── Fetch de pending-tasks ─────────────────────────────────────────────────
  const { data: pendingData, isError: fetchError } = useQuery({
    queryKey: ["pending-tasks", epicAdoId],
    queryFn: () => Tickets.listPendingTasks(epicAdoId),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: true,
  });

  const totalPending = pendingData?.total_pending ?? 0;
  const pendingTasks: PendingTaskItem[] = pendingData?.pending_tasks ?? [];

  // ── Handlers ──────────────────────────────────────────────────────────────
  // IMPORTANT: todos los hooks (incluidos los useCallback de abajo) deben
  // ejecutarse en TODOS los renders. Los early returns van AL FINAL, justo
  // antes del JSX, para no violar las Rules of Hooks.

  const handleOpen = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen(true);
    setSelected(new Set(pendingTasks.map((t) => t.rf_id)));
    setRfResults([]);
    setToast(null);
  }, [pendingTasks]);

  const handleClose = useCallback(() => {
    if (isRunning) return;
    setOpen(false);
    setReason("");
    setDryRun(false);
    setSelected(new Set());
    setRfResults([]);
  }, [isRunning]);

  const toggleSelect = useCallback((rfId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rfId)) next.delete(rfId);
      else next.add(rfId);
      return next;
    });
  }, []);

  const handleCreate = useCallback(async () => {
    if (isRunning || selected.size === 0) return;

    const tasksToRun = pendingTasks.filter((t) => selected.has(t.rf_id));
    setRfResults(
      tasksToRun.map((t) => ({ rf_id: t.rf_id, title: t.title, status: "pending" }))
    );
    setIsRunning(true);

    let createdCount = 0;
    let errorCount = 0;

    for (const task of tasksToRun) {
      setRfResults((prev) =>
        prev.map((r) => (r.rf_id === task.rf_id ? { ...r, status: "running" } : r))
      );

      try {
        const resp = await Tickets.createChildTask(epicAdoId, {
          pending_task_path: task.pending_task_path,
          operator_reason: reason.trim() || undefined,
          dry_run: dryRun,
        });

        let status: RfResult["status"] = "ok";
        if (resp.idempotent) status = "idempotent";
        else if (!resp.ok && resp.task_ado_id) status = "partial";
        else if (!resp.ok) status = "error";

        if (resp.ok || resp.task_ado_id) createdCount++;
        else errorCount++;

        setRfResults((prev) =>
          prev.map((r) =>
            r.rf_id === task.rf_id ? { ...r, status, response: resp } : r
          )
        );
      } catch (err) {
        errorCount++;
        setRfResults((prev) =>
          prev.map((r) =>
            r.rf_id === task.rf_id
              ? { ...r, status: "error", error: (err as Error).message }
              : r
          )
        );
      }
    }

    setIsRunning(false);

    // Invalidar queries
    qc.invalidateQueries({ queryKey: ["pending-tasks", epicAdoId] });
    qc.invalidateQueries({ queryKey: ["tickets"] });
    qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });

    // Toast resumen
    if (errorCount === 0) {
      setToast({ ok: true, message: `${createdCount} Task(s) creada(s) en ADO exitosamente.` });
      if (createdCount > 0) onTaskCreated?.();
    } else {
      setToast({
        ok: false,
        message: `${createdCount} ok, ${errorCount} con error. Revisar resultados.`,
      });
    }
  }, [epicAdoId, isRunning, selected, pendingTasks, reason, dryRun, qc, onTaskCreated]);

  const canCreate = selected.size > 0 && !isRunning;

  // ── Early returns (DESPUÉS de todos los hooks) ────────────────────────────
  // No renderizar si no hay pendientes (y no hay error de fetch)
  if (!fetchError && totalPending === 0 && pendingData !== undefined) {
    return null;
  }
  // Si hay error de fetch, no mostramos el botón tampoco (sin crashear el árbol)
  if (fetchError && pendingData === undefined) {
    return null;
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <button
        className={styles.btn}
        onClick={handleOpen}
        disabled={disabled || totalPending === 0}
        title={
          totalPending === 0
            ? "No hay Tasks pendientes de crear"
            : `Crear ${totalPending} Task(s) hija(s) en ADO`
        }
        aria-label={`Crear Tasks en ADO (${totalPending} pendiente${totalPending !== 1 ? "s" : ""})`}
      >
        Crear Tasks en ADO ({totalPending} pendiente{totalPending !== 1 ? "s" : ""})
      </button>

      {open && (
        <div
          className={styles.overlay}
          onClick={handleClose}
          role="dialog"
          aria-modal="true"
          aria-labelledby={`${modalId}-title`}
        >
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <header className={styles.header}>
              <h3 id={`${modalId}-title`} className={styles.title}>
                Crear Tasks en ADO
              </h3>
              <button
                className={styles.close}
                onClick={handleClose}
                disabled={isRunning}
                aria-label="Cerrar modal"
              >
                ✕
              </button>
            </header>

            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <span className={styles.epicTag}>EPIC-{epicAdoId}</span>
              <span className={styles.muted}>{totalPending} RF(s) pendiente(s) de crear en ADO</span>
            </div>

            {/* Lista de RFs */}
            <section className={styles.section}>
              <h4 className={styles.h4}>Requisitos funcionales pendientes</h4>
              <ul className={styles.rfList} role="list">
                {pendingTasks.map((task) => {
                  const result = rfResults.find((r) => r.rf_id === task.rf_id);
                  return (
                    <li key={task.rf_id} className={styles.rfItem}>
                      <input
                        type="checkbox"
                        id={`rf-${task.rf_id}`}
                        checked={selected.has(task.rf_id)}
                        onChange={() => toggleSelect(task.rf_id)}
                        disabled={isRunning || !!result}
                        aria-label={task.rf_id}
                      />
                      <label htmlFor={`rf-${task.rf_id}`} className={styles.rfInfo} style={{ cursor: "pointer" }}>
                        <div className={styles.rfId}>{task.rf_id}</div>
                        <div className={styles.rfTitle}>{task.title}</div>
                        <div className={styles.rfMeta}>
                          Plan:{" "}
                          {task.plan_exists
                            ? <span className={styles.rfPlanOk}>presente</span>
                            : <span className={styles.rfPlanMissing}>no encontrado — se omitira el adjunto</span>
                          }
                        </div>
                      </label>
                      {/* Indicador de estado */}
                      {result && (
                        <span style={{ fontSize: 11, fontWeight: 700 }}>
                          {result.status === "running" && <span style={{ color: "#60a5fa" }}>...</span>}
                          {result.status === "ok" && <span style={{ color: "#4ade80" }}>OK</span>}
                          {result.status === "idempotent" && <span style={{ color: "#a78bfa" }}>YA EXISTIA</span>}
                          {result.status === "partial" && <span style={{ color: "#fbbf24" }}>PARCIAL</span>}
                          {result.status === "error" && <span style={{ color: "#f87171" }}>ERROR</span>}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>

            {/* Formulario */}
            <section className={styles.section}>
              <label className={styles.label}>
                Motivo del operador <span className={styles.opt}>(opcional)</span>
              </label>
              <textarea
                className={styles.textarea}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Ej: Revisado con el equipo técnico, listo para análisis"
                rows={2}
                disabled={isRunning}
              />
              <label className={styles.inlineLabel}>
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  disabled={isRunning}
                />{" "}
                Dry run — solo validar, no crear en ADO
              </label>
            </section>

            {/* Resultados */}
            {rfResults.length > 0 && (
              <section className={styles.section}>
                <h4 className={styles.h4}>Resultados</h4>
                <ul className={styles.results}>
                  {rfResults.map((r) => (
                    <li
                      key={r.rf_id}
                      className={
                        r.status === "ok" || r.status === "idempotent"
                          ? styles.resultOk
                          : r.status === "partial"
                          ? styles.resultWarn
                          : r.status === "error"
                          ? styles.resultFail
                          : undefined
                      }
                    >
                      <div>
                        <strong>{r.rf_id}</strong>
                        {r.status === "running" && " — procesando..."}
                        {r.status === "ok" && r.response?.task_url && (
                          <>
                            {" — Task "}
                            <a
                              href={r.response.task_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={styles.resultLink}
                            >
                              ADO-{r.response.task_ado_id}
                            </a>
                            {" creada"}
                          </>
                        )}
                        {r.status === "idempotent" && r.response?.task_url && (
                          <>
                            {" — ya existia: "}
                            <a
                              href={r.response.task_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={styles.resultLink}
                            >
                              ADO-{r.response.task_ado_id}
                            </a>
                          </>
                        )}
                        {r.status === "partial" && ` — Task ADO-${r.response?.task_ado_id} creada, adjunto falló`}
                        {r.status === "error" && ` — Error: ${r.error ?? r.response?.message ?? "desconocido"}`}
                      </div>
                      {r.response?.human_action_required && (
                        <div className={styles.humanAction}>
                          {r.response.human_action_required}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Toast interno */}
            {toast && (
              <div
                role="alert"
                aria-live="assertive"
                className={toast.ok ? styles.resultOk : styles.errorMsg}
                style={{ padding: "8px 10px", borderRadius: 4, fontSize: 12, marginTop: 8 }}
              >
                {toast.message}
              </div>
            )}

            {/* Footer */}
            <footer className={styles.footer}>
              <button
                className={styles.cancel}
                onClick={handleClose}
                disabled={isRunning}
              >
                {rfResults.length > 0 ? "Cerrar" : "Cancelar"}
              </button>
              <button
                className={styles.primary}
                onClick={handleCreate}
                disabled={!canCreate}
                aria-label={dryRun ? "Simular creación (dry run)" : "Crear Task en ADO"}
              >
                {isRunning
                  ? "Procesando..."
                  : dryRun
                  ? "Simular (dry run)"
                  : `Crear Task en ADO (${selected.size})`}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}

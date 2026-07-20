import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Executions, Agents } from "../api/endpoints";
import type { AgentExecution } from "../types";
import { useWorkbench } from "../store/workbench";
import { fetchReviewInbox, reviewInboxQueryKey } from "../services/reviewInbox";
import ExecutionDetailDrawer from "../components/ExecutionDetailDrawer";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import { StatusChip, Checkbox } from "../components/ui";
import Toast, { type ToastState } from "../components/Toast";
import BulkActionsBar from "../components/bulk/BulkActionsBar";
import { useRowSelection } from "../components/bulk/useRowSelection";
import { useBulkActionsEnabled } from "../services/bulkFlags";
import { capExecutionBatch, createBulkRunner, summarizeBulk, type BulkWorker } from "../services/bulkModel";
import { runStatusTone, runStatusLabel } from "../utils/runStatus";
import { formatRelativeTime } from "../utils/formatRelativeTime";
import styles from "./ReviewInboxPage.module.css";

function summarizeCause(exec: { error_message?: string | null; metadata?: Record<string, unknown>; contract_result?: { passed?: boolean; failures?: Array<{ message?: string }> } | null }): string {
  const metadata = (exec.metadata ?? {}) as Record<string, unknown>;
  const failureKind = metadata.failure_kind ? String(metadata.failure_kind) : "";
  if (failureKind) return failureKind;

  const contract = exec.contract_result;
  if (contract && contract.passed === false && Array.isArray(contract.failures) && contract.failures.length > 0) {
    return String(contract.failures[0]?.message || "contract failed");
  }

  return String(exec.error_message || "requiere revisión").split("\n")[0].slice(0, 160);
}

export default function ReviewInboxPage() {
  const qc = useQueryClient();
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const [detailExecutionId, setDetailExecutionId] = useState<number | null>(null);
  const [busyExecutionId, setBusyExecutionId] = useState<number | null>(null);

  // ── Plan 187 — selección múltiple y acciones en lote ─────────────────────────
  const bulkEnabled = useBulkActionsEnabled();
  const [bulkToast, setBulkToast] = useState<ToastState | null>(null);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const runnerRef = useRef(createBulkRunner());
  const headerWrapRef = useRef<HTMLSpanElement>(null);
  const bulkRunning = bulkProgress !== null;

  const executionsQ = useQuery({
    queryKey: reviewInboxQueryKey(activeProjectName),
    queryFn: () => fetchReviewInbox(activeProjectName),
    refetchInterval: 30000,
  });

  const rows = executionsQ.data ?? [];

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const ta = new Date(a.completed_at || a.started_at).getTime();
      const tb = new Date(b.completed_at || b.started_at).getTime();
      return tb - ta;
    });
  }, [rows]);

  const visibleIds = useMemo(() => sortedRows.map((r) => r.id), [sortedRows]);
  const sel = useRowSelection({
    visibleIds,
    enabled: bulkEnabled,
    escapeDisabled: detailExecutionId !== null || bulkRunning,
  });

  // Auto-ocultado del Toast agregado (8 s, con cleanup).
  useEffect(() => {
    if (!bulkToast) return;
    const t = setTimeout(() => setBulkToast(null), 8000);
    return () => clearTimeout(t);
  }, [bulkToast]);

  // Tri-estado de la cabecera (propiedad del DOM, NO estilo — Checkbox sin forwardRef).
  useEffect(() => {
    const el = headerWrapRef.current?.querySelector("input");
    if (el) el.indeterminate = sel.header === "some";
  }, [sel.header]);

  // C3 — cuerpo del relanzamiento compartido por el botón por fila y el lote
  // (mismo payload de Agents.run; cero drift entre caminos).
  async function relaunchRow(execution: AgentExecution): Promise<void> {
    await Agents.run({
      agent_type: execution.agent_type,
      ticket_id: execution.ticket_id,
      context_blocks: [],
      project: activeProjectName ?? undefined,
    });
  }

  const relaunch = async (executionId: number) => {
    const execution = rows.find((x) => x.id === executionId);
    if (!execution) return;
    setBusyExecutionId(executionId);
    try {
      await relaunchRow(execution);
      await qc.invalidateQueries({ queryKey: ["review-inbox", activeProjectName] });
      await qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
      await qc.invalidateQueries({ queryKey: ["executions"] });
    } finally {
      setBusyExecutionId(null);
    }
  };

  const discard = async (executionId: number) => {
    setBusyExecutionId(executionId);
    try {
      await Executions.discard(executionId);
      await qc.invalidateQueries({ queryKey: ["review-inbox", activeProjectName] });
    } finally {
      setBusyExecutionId(null);
    }
  };

  // Ejecutor del lote: reusa los endpoints por ítem existentes, secuencial.
  async function runBulkAction(kind: "discard" | "relaunch") {
    const ids = sel.orderedSelectedIds;
    if (kind === "relaunch") {
      const cap = capExecutionBatch(ids); // C5: freno de costo para acciones que disparan ejecuciones
      if (!cap.ok) {
        setBulkToast(cap.toast);
        return;
      }
    }
    const worker: BulkWorker =
      kind === "discard"
        ? async (id) => {
            await Executions.discard(id);
          }
        : async (id) => {
            const row = rows.find((x) => x.id === id);
            if (!row) throw new Error("la fila ya no está en la bandeja");
            await relaunchRow(row); // C3: MISMA función que el botón por fila
          };
    const p = runnerRef.current.run(ids, worker, (done, total) => setBulkProgress({ done, total }));
    if (!p) return; // guard: ya hay un lote corriendo
    setBulkProgress({ done: 0, total: ids.length });
    const result = await p;
    setBulkProgress(null);
    setBulkToast(
      kind === "discard"
        ? summarizeBulk(result, "ejecución descartada", "ejecuciones descartadas")
        : summarizeBulk(result, "ejecución relanzada", "ejecuciones relanzadas"),
    );
    sel.retainFailed(result.failed.map((f) => f.id)); // C1: retención funcional, sin snapshot stale
    await qc.invalidateQueries({ queryKey: ["review-inbox", activeProjectName] });
    if (kind === "relaunch") {
      await qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
      await qc.invalidateQueries({ queryKey: ["executions"] });
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2>Bandeja de revisión</h2>
        <span className={styles.counter}>{sortedRows.length}</span>
      </div>

      {executionsQ.isLoading && <SkeletonList rows={6} rowHeight={28} ariaLabel="Cargando ejecuciones" />}
      {!executionsQ.isLoading && !executionsQ.isError && sortedRows.length === 0 && (
        <EmptyState variant="review" />
      )}

      {sortedRows.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              {bulkEnabled && (
                <th className={styles.selectCell}>
                  <span ref={headerWrapRef}>
                    <Checkbox
                      label=""
                      aria-label="Seleccionar todo lo visible"
                      checked={sel.header === "all"}
                      onChange={() => {}}
                      onClick={(e) => {
                        e.stopPropagation();
                        sel.onToggleAll();
                      }}
                    />
                  </span>
                </th>
              )}
              <th>Ticket</th>
              <th>Agente</th>
              <th>Status</th>
              <th>Causa</th>
              <th>Terminado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr key={row.id}>
                {bulkEnabled && (
                  <td className={styles.selectCell}>
                    <Checkbox
                      label=""
                      aria-label={`Seleccionar ejecución #${row.id}`}
                      checked={sel.isRowSelected(row.id)}
                      onChange={() => {}}
                      onClick={(e) => sel.onRowCheckboxClick(row.id, e)}
                    />
                  </td>
                )}
                <td>#{row.ticket_id}</td>
                <td>{row.agent_type}</td>
                <td><StatusChip tone={runStatusTone(row.status)} size="sm">{runStatusLabel(row.status)}</StatusChip></td>
                <td title={row.error_message || undefined}>{summarizeCause(row)}</td>
                <td>{formatRelativeTime(row.completed_at || row.started_at)}</td>
                <td className={styles.actions}>
                  <button onClick={() => setDetailExecutionId(row.id)}>Ver detalle</button>
                  <button onClick={() => void relaunch(row.id)} disabled={busyExecutionId === row.id}>
                    Relanzar
                  </button>
                  <button onClick={() => void discard(row.id)} disabled={busyExecutionId === row.id}>
                    Descartar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {bulkEnabled && (
        <BulkActionsBar
          count={sel.count}
          running={bulkRunning}
          progress={bulkProgress}
          onClear={sel.clear}
          actions={[
            {
              id: "discard-selected",
              destructive: true,
              label: (n) => `Descartar ${n}`,
              armedLabel: (n) => `¿Descartar ${n}? Confirmar`,
              run: () => void runBulkAction("discard"),
            },
            {
              id: "relaunch-selected",
              destructive: true,
              label: (n) => `Relanzar ${n}`,
              armedLabel: (n) => `¿Relanzar ${n}? Confirmar`,
              run: () => void runBulkAction("relaunch"),
            },
          ]}
        />
      )}
      {bulkToast && <Toast toast={bulkToast} onClose={() => setBulkToast(null)} />}

      <ExecutionDetailDrawer executionId={detailExecutionId} onClose={() => setDetailExecutionId(null)} />
    </div>
  );
}

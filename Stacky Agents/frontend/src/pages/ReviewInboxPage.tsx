import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Executions, Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { fetchReviewInbox, reviewInboxQueryKey } from "../services/reviewInbox";
import ExecutionDetailDrawer from "../components/ExecutionDetailDrawer";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import { StatusChip } from "../components/ui";
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

  const relaunch = async (executionId: number) => {
    const execution = rows.find((x) => x.id === executionId);
    if (!execution) return;
    setBusyExecutionId(executionId);
    try {
      await Agents.run({
        agent_type: execution.agent_type,
        ticket_id: execution.ticket_id,
        context_blocks: [],
        project: activeProjectName ?? undefined,
      });
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

      <ExecutionDetailDrawer executionId={detailExecutionId} onClose={() => setDetailExecutionId(null)} />
    </div>
  );
}

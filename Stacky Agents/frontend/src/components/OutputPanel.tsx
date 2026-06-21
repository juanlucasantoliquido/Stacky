import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import ConfidenceBadge from "./ConfidenceBadge";
import ContractBadge from "./ContractBadge";
import DossierPanel from "./DossierPanel";
import EpicChildrenPanel from "./EpicChildrenPanel";
import NextAgentSuggestion from "./NextAgentSuggestion";
import OutputTools from "./OutputTools";
import StructuredOutput from "./StructuredOutput";
import styles from "./OutputPanel.module.css";

export default function OutputPanel() {
  const { activeExecutionId, runningExecutionId, setRunningExecution } = useWorkbench();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [reviewError, setReviewError] = useState<string | null>(null);

  const stream = useExecutionStream(runningExecutionId);

  useEffect(() => {
    if (runningExecutionId != null && stream.done) {
      setRunningExecution(null);
    }
  }, [stream.done, runningExecutionId, setRunningExecution]);

  const { data: execution } = useQuery({
    queryKey: ["execution", activeExecutionId],
    queryFn: () => Executions.byId(activeExecutionId!),
    enabled: activeExecutionId != null,
    refetchInterval: (q) => {
      const status = (q.state.data as any)?.status;
      return status === "preparing" || status === "running" ? 1500 : false;
    },
  });

  const approve = useMutation({
    mutationFn: (id: number) => Executions.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["execution", activeExecutionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });
  const discard = useMutation({
    mutationFn: (id: number) => Executions.discard(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["execution", activeExecutionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });
  const humanReview = useMutation({
    mutationFn: (payload: { id: number; verdict: "approved" | "rejected" | "approved_with_notes"; note?: string }) =>
      Executions.humanReview(payload.id, { verdict: payload.verdict, note: payload.note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["execution", activeExecutionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
      setNote("");
      setReviewError(null);
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || error?.message || "Error submitting review";
      setReviewError(msg);
    },
  });
  const publish = useMutation({
    mutationFn: (id: number) => Executions.publish(id),
  });

  if (!activeExecutionId && runningExecutionId == null) {
    return (
      <section className={styles.section}>
        <header className={styles.head}>OUTPUT</header>
        <div className={styles.empty}>
          <p className="muted">
            Seleccioná un agente y presioná <strong>Run</strong>.
          </p>
        </div>
      </section>
    );
  }

  if (runningExecutionId != null && !execution) {
    return (
      <section className={styles.section}>
        <header className={styles.head}>OUTPUT — running…</header>
        <div className={styles.empty}>
          <p className="muted">El agente está procesando. Mirá los logs abajo.</p>
        </div>
      </section>
    );
  }

  if (!execution) return null;

  return (
    <>
    <section className={styles.section}>
      <header className={styles.head}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>OUTPUT — exec #{execution.id} — {execution.agent_type}</span>
          {!!execution.metadata?.from_cache && (
            <span title="Output servido desde cache" style={{ color: "var(--success)" }}>
              🔁 cached
            </span>
          )}
          {(() => {
            const conf = execution.metadata?.confidence as
              | { overall: number; signals?: string[] }
              | undefined;
            return conf ? (
              <ConfidenceBadge overall={conf.overall} signals={conf.signals} />
            ) : null;
          })()}
        </span>
        <span className={styles.status} data-status={execution.status}>
          {execution.status}
          {execution.verdict ? ` (${execution.verdict})` : ""}
        </span>
      </header>
      <div className={styles.body}>
        {execution.status === "preparing" && (
          <p className="muted">preparando workspace...</p>
        )}
        {execution.status === "running" && (
          <p className="muted">streaming…</p>
        )}
        {execution.status === "error" && (
          <pre className={styles.error}>{execution.error_message}</pre>
        )}
        {execution.output && (
          <>
            {/* N1 — Contract Validator badge */}
            {execution.contract_result && (
              <ContractBadge result={execution.contract_result} />
            )}
            {/* N2 — Structured Output Renderer */}
            <StructuredOutput
              output={execution.output}
              agentType={execution.agent_type}
            />
          </>
        )}
      </div>
      {(execution.status === "completed" || execution.status === "needs_review") && (
        <>
          {execution.metadata?.human_review && (
            <div style={{ padding: 12, borderTop: "1px solid var(--border)", backgroundColor: "var(--bg-elev)", fontSize: 12 }}>
              <div style={{ color: "var(--text-muted)" }}>
                Reviewed: <strong>{(execution.metadata.human_review as any).verdict}</strong>
                {(execution.metadata.human_review as any).reviewed_by && ` — ${(execution.metadata.human_review as any).reviewed_by}`}
              </div>
            </div>
          )}
          {!execution.verdict && (
            <>
              <footer className={styles.actions}>
                <button
                  className={styles.primary}
                  onClick={() => humanReview.mutate({ id: execution.id, verdict: "approved" })}
                  disabled={humanReview.isPending}
                >
                  Aprobar
                </button>
                <button
                  className={styles.secondary}
                  onClick={() => humanReview.mutate({ id: execution.id, verdict: "rejected" })}
                  disabled={humanReview.isPending}
                >
                  Rechazar
                </button>
                <button
                  className={styles.secondary}
                  onClick={() => {
                    if (note.trim()) {
                      humanReview.mutate({ id: execution.id, verdict: "approved_with_notes", note });
                    }
                  }}
                  disabled={humanReview.isPending || !note.trim()}
                >
                  Aprobar con notas
                </button>
              </footer>
              <div style={{ padding: 12, backgroundColor: "var(--bg-elev)", borderTop: "1px solid var(--border)" }}>
                <textarea
                  value={note}
                  onChange={(e) => {
                    const val = e.target.value.slice(0, 2000);
                    setNote(val);
                    setReviewError(null);
                  }}
                  placeholder="Agregar nota (máx 2000 caracteres)..."
                  style={{
                    width: "100%",
                    height: 80,
                    padding: 8,
                    fontFamily: "var(--font-sans)",
                    fontSize: 12,
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--bg-panel)",
                    color: "var(--text-primary)",
                    boxSizing: "border-box",
                    resize: "vertical",
                  }}
                />
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                  {note.length}/2000
                </div>
                {reviewError && (
                  <div style={{ fontSize: 12, color: "var(--danger)", marginTop: 8 }}>
                    {reviewError}
                  </div>
                )}
              </div>
            </>
          )}
          {!execution.metadata?.human_review && execution.status === "completed" && (
            <footer className={styles.actions}>
              <button
                className={styles.secondary}
                onClick={() => publish.mutate(execution.id)}
                disabled={publish.isPending}
              >
                Send to ADO
              </button>
            </footer>
          )}
        </>
      )}
      {execution.status === "completed" && execution.output && (
        <OutputTools
          executionId={execution.id}
          agentType={execution.agent_type}
          output={execution.output}
        />
      )}
      {/* Plan 59 — Descomposición vertical épica→hijos (flag STACKY_EPIC_DECOMPOSITION_ENABLED, default OFF) */}
      {execution.status === "completed" &&
        execution.output &&
        typeof execution.metadata?.epic_ado_id === "number" && (
          <EpicChildrenPanel
            output={execution.output}
            epicAdoId={execution.metadata.epic_ado_id as number}
            projectName={typeof execution.metadata?.project_name === "string" ? execution.metadata.project_name : undefined}
          />
        )}
      {execution.verdict === "approved" && (
        <div style={{ padding: 12, borderTop: "1px solid var(--border)" }}>
          <NextAgentSuggestion afterAgent={execution.agent_type} />
        </div>
      )}
    </section>
    {/* QA UAT dossier — only shown for qa agent executions with pipeline metadata */}
    {execution.agent_type === "qa" && (
      <DossierPanel execution={execution} />
    )}
  </>
  );
}

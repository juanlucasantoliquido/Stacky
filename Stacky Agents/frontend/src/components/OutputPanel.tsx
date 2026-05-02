import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import ConfidenceBadge from "./ConfidenceBadge";
import ContractBadge from "./ContractBadge";
import DossierPanel from "./DossierPanel";
import NextAgentSuggestion from "./NextAgentSuggestion";
import OutputTools from "./OutputTools";
import StructuredOutput from "./StructuredOutput";
import styles from "./OutputPanel.module.css";

export default function OutputPanel() {
  const { activeExecutionId, runningExecutionId, setRunningExecution } = useWorkbench();
  const qc = useQueryClient();

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
      return status === "running" ? 1500 : false;
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
      {execution.status === "completed" && !execution.verdict && (
        <footer className={styles.actions}>
          <button
            className={styles.primary}
            onClick={() => approve.mutate(execution.id)}
            disabled={approve.isPending}
          >
            Approve
          </button>
          <button
            className={styles.secondary}
            onClick={() => publish.mutate(execution.id)}
            disabled={publish.isPending}
          >
            Send to ADO
          </button>
          <button
            className={styles.secondary}
            onClick={() => discard.mutate(execution.id)}
            disabled={discard.isPending}
          >
            Discard
          </button>
        </footer>
      )}
      {execution.status === "completed" && execution.output && (
        <OutputTools
          executionId={execution.id}
          agentType={execution.agent_type}
          output={execution.output}
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

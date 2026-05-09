/*
 * DossierPanel — QA UAT dossier viewer
 *
 * Renders the pipeline_result of a QA UAT execution:
 *   - Verdict badge (PASS / FAIL / BLOCKED / MIXED)
 *   - Data Readiness button (Sprint 9): shown when verdict=BLOCKED + category=DATA
 *   - Stage pipeline summary table
 *   - Scenario results table with per-assertion detail
 *   - Failure analysis section (data_drift, regression, etc.)
 *   - Artifact links (trace.zip, video.webm, dossier.json)
 *
 * Displayed below OutputPanel when the active execution has
 * agent_type="qa" and a pipeline_result in metadata.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { QaUat } from "../api/endpoints";
import type { QaUatRunStatus } from "../api/endpoints";
import type { AgentExecution } from "../types";
import DataReadinessModal from "./DataReadinessModal";
import SeedPreviewPanel from "./SeedPreviewPanel";
import CatalogDashboard from "./CatalogDashboard";
import OracleDashboard from "./OracleDashboard";
import ConfidenceDashboard from "./ConfidenceDashboard";
import styles from "./DossierPanel.module.css";

// ── Types ─────────────────────────────────────────────────────────────────────

interface PipelineResult {
  ok: boolean;
  ticket_id: number;
  verdict?: "PASS" | "FAIL" | "BLOCKED" | "MIXED";
  elapsed_s?: number;
  stages?: Record<string, StageResult>;
}

interface StageResult {
  ok: boolean;
  skipped?: boolean;
  reason?: string;
  error?: string;
  scenario_count?: number;
  generated?: number;
  blocked?: number;
  total?: number;
  pass?: number;
  fail?: number;
  "ok_count"?: number;
  analyzed?: number;
  categories?: Record<string, number>;
  verdict?: string;
  publish_state?: string;
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface DossierPanelProps {
  execution: AgentExecution;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DossierPanel({ execution }: DossierPanelProps) {
  const qaRunId: string | undefined =
    (execution.metadata as any)?.qa_uat_execution_id;

  // Sprint 9 — Data Readiness modal state
  const [showDataReadiness, setShowDataReadiness] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["qa-uat-run", qaRunId],
    queryFn: () => QaUat.status(qaRunId!),
    enabled: qaRunId != null,
    refetchInterval: (q) => {
      const status = (q.state.data as QaUatRunStatus | undefined)?.status;
      return status === "running" || status === "queued" ? 2000 : false;
    },
  });

  if (!qaRunId) return null;

  if (isLoading) {
    return (
      <section className={styles.panel}>
        <header className={styles.head}>QA UAT DOSSIER</header>
        <div className={styles.loading}>cargando pipeline…</div>
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className={styles.panel}>
        <header className={styles.head}>QA UAT DOSSIER</header>
        <div className={styles.error}>Error al cargar el resultado del pipeline.</div>
      </section>
    );
  }

  const running = data.status === "running" || data.status === "queued";
  const pr = data.pipeline_result;

  // Sprint 9: detect DATA-blocked state to show Data Readiness button
  const isDataBlocked =
    pr?.verdict === "BLOCKED" &&
    (pr?.category === "DATA" || pr?.failed_stage?.includes("data_readiness") || pr?.failed_stage?.includes("data_resolution"));

  // Sprint 10: detect SQL_SEED_APPROVAL_REQUIRED state to show SeedPreviewPanel
  const isSeedApprovalRequired =
    pr?.verdict === "BLOCKED" &&
    (pr?.category === "SQL_SEED" ||
     pr?.reason === "SQL_SEED_APPROVAL_REQUIRED" ||
     pr?.failed_stage?.includes("sql_seed"));

  // Sprint 12: detect CATALOG_EMPTY state to show CatalogDashboard
  const hasCatalogIssues =
    (pr?.stages?.catalog_readiness as any)?.empty_count > 0 ||
    (pr?.stages?.catalog_readiness as any)?.blocking_empty_count > 0;

  // Sprint 13: detect oracle/weak assertion issues to show OracleDashboard
  const hasOracleIssues =
    (pr?.stages?.oracle_evaluation as any)?.weak_tests > 0 ||
    (pr?.stages?.oracle_evaluation as any)?.no_oracle_count > 0 ||
    (pr?.stages?.oracle_evaluation as any)?.oracle_publish_blocked === true;

  // Sprint 14: detect low confidence to show ConfidenceDashboard
  const hasConfidenceIssues =
    (pr?.stages?.test_confidence as any)?.low_count > 0 ||
    (pr?.stages?.test_confidence as any)?.publish_blocked === true;

  // Extract ticket_id from pipeline result for data requests
  const pipelineTicketId = pr?.ticket_id ?? (execution.metadata as any)?.pipeline_ticket_id;

  return (
    <>
      <section className={styles.panel}>
        <header className={styles.head}>
          <span>QA UAT DOSSIER</span>
          <div className={styles.headRight}>
            {running && <span className={styles.running}>● RUNNING</span>}
            {pr?.verdict && <VerdictBadge verdict={pr.verdict} />}
            {pr?.elapsed_s != null && (
              <span className={styles.elapsed}>{pr.elapsed_s.toFixed(1)}s</span>
            )}
            {/* Sprint 9: Data Readiness button — only visible when pipeline is BLOCKED DATA */}
            {isDataBlocked && pipelineTicketId && (
              <button
                onClick={() => setShowDataReadiness(true)}
                style={{
                  marginLeft: "0.5rem",
                  background: "#b85000",
                  border: "none",
                  color: "#fff",
                  borderRadius: "4px",
                  padding: "0.2rem 0.6rem",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  cursor: "pointer",
                  letterSpacing: "0.03em",
                }}
                title="Resolver datos faltantes para continuar el pipeline"
              >
                🔒 DATOS FALTANTES
              </button>
            )}
          </div>
        </header>

        {running && !pr && (
          <div className={styles.runningMsg}>Pipeline en ejecución…</div>
        )}

        {pr && (
          <div className={styles.body}>
            {/* Sprint 9: data blocked info banner */}
            {isDataBlocked && (
              <div
                style={{
                  background: "rgba(184, 80, 0, 0.15)",
                  border: "1px solid rgba(184, 80, 0, 0.5)",
                  borderRadius: "6px",
                  padding: "0.7rem 1rem",
                  marginBottom: "0.75rem",
                  fontSize: "0.82rem",
                  lineHeight: 1.5,
                  color: "#ffa07a",
                }}
              >
                <strong>Pipeline bloqueado por falta de datos</strong>
                {pr.reason && <span> — {pr.reason}</span>}
                {pr.human_action_required && (
                  <div style={{ marginTop: "0.3rem", color: "#cccccc" }}>
                    {pr.human_action_required}
                  </div>
                )}
                <div style={{ marginTop: "0.5rem" }}>
                  <button
                    onClick={() => setShowDataReadiness(true)}
                    style={{
                      background: "#b85000",
                      border: "none",
                      color: "#fff",
                      borderRadius: "4px",
                      padding: "0.35rem 0.85rem",
                      fontSize: "0.8rem",
                      cursor: "pointer",
                    }}
                  >
                    Resolver datos faltantes
                  </button>
                </div>
              </div>
            )}
            {pr.stages && <StageTable stages={pr.stages as Record<string, StageResult>} />}

            {/* Sprint 10: SQL Seed Preview — shown when pipeline is awaiting seed approval */}
            {isSeedApprovalRequired && pipelineTicketId && (
              <SeedPreviewPanel
                runId={String(pipelineTicketId)}
                ticketId={Number(pipelineTicketId)}
              />
            )}

            {/* Sprint 12: Catalog Dashboard — shown when catalog issues detected */}
            {hasCatalogIssues && pipelineTicketId && (
              <CatalogDashboard
                runId={String(pipelineTicketId)}
                ticketId={Number(pipelineTicketId)}
              />
            )}

            {/* Sprint 13: Oracle Dashboard — shown when oracle/weak assertion issues detected */}
            {hasOracleIssues && pipelineTicketId && (
              <OracleDashboard
                runId={String(pipelineTicketId)}
                ticketId={Number(pipelineTicketId)}
              />
            )}

            {/* Sprint 14: Confidence Dashboard — shown when confidence is low or blocked */}
            {hasConfidenceIssues && pipelineTicketId && (
              <ConfidenceDashboard
                runId={String(pipelineTicketId)}
                ticketId={Number(pipelineTicketId)}
              />
            )}

            <EvidenceSection metadata={execution.metadata} />
          </div>
        )}

        {data.status === "error" && (
          <div className={styles.error}>
            Pipeline falló: {data.error ?? "error desconocido"}
          </div>
        )}
      </section>

      {/* Sprint 9: Data Readiness Modal */}
      {showDataReadiness && pipelineTicketId && (
        <DataReadinessModal
          runId={String(pipelineTicketId)}
          ticketId={Number(pipelineTicketId)}
          onClose={() => setShowDataReadiness(false)}
          onResolved={() => {
            setShowDataReadiness(false);
            // Optionally: trigger pipeline resume (out of scope for Sprint 9)
          }}
        />
      )}
    </>
  );
}

// ── VerdictBadge ──────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className={styles.verdict}
      data-verdict={verdict}
      aria-label={`Verdict: ${verdict}`}
    >
      {verdict === "PASS" && "✓ "}
      {verdict === "FAIL" && "✗ "}
      {verdict === "BLOCKED" && "⊘ "}
      {verdict === "MIXED" && "◑ "}
      {verdict}
    </span>
  );
}

// ── StageTable ────────────────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  reader: "Ticket reader",
  ui_map: "UI map builder",
  compiler: "Scenario compiler",
  preconditions: "Precondition check",
  generator: "Test generator",
  runner: "Test runner",
  evaluator: "Assertion evaluator",
  failure_analyzer: "Failure analyzer",
  dossier: "Dossier builder",
  publisher: "ADO publisher",
};

const STAGE_ORDER = [
  "reader", "ui_map", "compiler", "preconditions",
  "generator", "runner", "evaluator", "failure_analyzer",
  "dossier", "publisher",
];

function StageTable({ stages }: { stages: Record<string, StageResult> }) {
  const [expanded, setExpanded] = useState(false);

  const rows = STAGE_ORDER
    .filter((s) => s in stages)
    .map((s) => ({ key: s, label: STAGE_LABELS[s] ?? s, ...stages[s] }));

  return (
    <div className={styles.section}>
      <button
        className={styles.sectionToggle}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className={styles.sectionTitle}>PIPELINE STAGES</span>
        <span className={styles.chevron}>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td className={styles.stageLabel}>{row.label}</td>
                <td>
                  <StageStatus ok={row.ok} skipped={row.skipped} />
                </td>
                <td className={styles.stageDetail}>
                  <StageDetail stage={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StageStatus({ ok, skipped }: { ok: boolean; skipped?: boolean }) {
  if (skipped) return <span className={styles.skipped}>SKIPPED</span>;
  if (ok) return <span className={styles.ok}>OK</span>;
  return <span className={styles.fail}>FAIL</span>;
}

function StageDetail({ stage }: { stage: StageResult & { key: string } }) {
  const parts: string[] = [];

  if (stage.scenario_count != null) parts.push(`${stage.scenario_count} scenarios`);
  if (stage.generated != null) parts.push(`${stage.generated} generated`);
  if (stage.pass != null) parts.push(`${stage.pass} pass`);
  if (stage.fail != null && stage.fail > 0) parts.push(`${stage.fail} fail`);
  if (stage.blocked != null && stage.blocked > 0) parts.push(`${stage.blocked} blocked`);
  if (stage.analyzed != null) parts.push(`${stage.analyzed} analyzed`);
  if (stage.categories) {
    const cats = Object.entries(stage.categories)
      .map(([k, v]) => `${k}:${v}`)
      .join(", ");
    if (cats) parts.push(cats);
  }
  if (stage.verdict) parts.push(stage.verdict);
  if (stage.publish_state) parts.push(stage.publish_state);
  if (stage.reason) parts.push(stage.reason);
  if (stage.error) parts.push(`⚠ ${stage.error}`);

  return <span>{parts.join(" · ") || "—"}</span>;
}

// ── EvidenceSection ───────────────────────────────────────────────────────────

function EvidenceSection({ metadata }: { metadata?: Record<string, unknown> | null }) {
  const evidencePaths: string[] = [];

  if (metadata?.dossier_path) evidencePaths.push(metadata.dossier_path as string);
  if (metadata?.evidence_dir) evidencePaths.push(metadata.evidence_dir as string);

  if (evidencePaths.length === 0) return null;

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>EVIDENCIA</div>
      <ul className={styles.artifactList}>
        {evidencePaths.map((p) => (
          <li key={p}>
            <span className={styles.artifactPath} title={p}>
              {p.split(/[\\/]/).slice(-2).join("/")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

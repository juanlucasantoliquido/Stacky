/*
 * DossierPanel — QA UAT dossier viewer
 *
 * Renders the pipeline_result of a QA UAT execution:
 *   - Verdict badge (PASS / FAIL / BLOCKED / MIXED)
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

  return (
    <section className={styles.panel}>
      <header className={styles.head}>
        <span>QA UAT DOSSIER</span>
        <div className={styles.headRight}>
          {running && <span className={styles.running}>● RUNNING</span>}
          {pr?.verdict && <VerdictBadge verdict={pr.verdict} />}
          {pr?.elapsed_s != null && (
            <span className={styles.elapsed}>{pr.elapsed_s.toFixed(1)}s</span>
          )}
        </div>
      </header>

      {running && !pr && (
        <div className={styles.runningMsg}>Pipeline en ejecución…</div>
      )}

      {pr && (
        <div className={styles.body}>
          {pr.stages && <StageTable stages={pr.stages} />}
          <EvidenceSection metadata={execution.metadata} />
        </div>
      )}

      {data.status === "error" && (
        <div className={styles.error}>
          Pipeline falló: {data.error ?? "error desconocido"}
        </div>
      )}
    </section>
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

/**
 * OracleDashboard.tsx — Sprint 13: Oracle Engine + Weak Assertion Detector
 *
 * Renders oracle evaluation results and weak assertion warnings for a QA UAT run.
 *
 * Features:
 *  - Per-scenario oracle verdict (PASS / FAIL / NO_ORACLE / WEAK_ONLY / SKIP)
 *  - P0 blocking indicator when a critical scenario has no oracle
 *  - Weak assertion findings from Playwright spec analysis
 *  - On-demand oracle re-evaluation trigger
 *
 * Used inside DossierPanel when `stages.oracle_evaluation.weak_tests > 0`
 * or `stages.oracle_evaluation.no_oracle_count > 0`.
 *
 * Props:
 *   runId    — pipeline run_id
 *   ticketId — ADO ticket ID
 *
 * Security:
 *   - Read-only display of evidence artifacts.
 *   - On-demand evaluation is safe: no DB writes, no test execution.
 */
import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import type {
  OracleEvaluationResult,
  ScenarioOracleResult,
  WeakAssertionReport,
  FileAssertionAnalysis,
} from "../api/endpoints";
import styles from "./OracleDashboard.module.css";

// ── Verdict badge ─────────────────────────────────────────────────────────────

type VerdictBadgeProps = {
  verdict: string;
  small?: boolean;
};

const VERDICT_COLORS: Record<string, string> = {
  PASS: "#16a34a",
  FAIL: "#dc2626",
  NO_ORACLE: "#9333ea",
  WEAK_ONLY: "#d97706",
  SKIP: "#6b7280",
  ERROR: "#b91c1c",
};

function VerdictBadge({ verdict, small }: VerdictBadgeProps) {
  const color = VERDICT_COLORS[verdict] ?? "#374151";
  return (
    <span
      className={styles.verdictBadge}
      style={{ background: color, fontSize: small ? "11px" : "13px" }}
      title={verdict}
    >
      {verdict}
    </span>
  );
}

// ── Strength badge ────────────────────────────────────────────────────────────

const STRENGTH_COLORS: Record<string, string> = {
  P0: "#16a34a",
  P1: "#2563eb",
  P2: "#d97706",
  NONE: "#6b7280",
};

function StrengthBadge({ strength }: { strength: string }) {
  return (
    <span
      className={styles.strengthBadge}
      style={{ background: STRENGTH_COLORS[strength] ?? "#374151" }}
      title={`Oracle strength: ${strength}`}
    >
      {strength}
    </span>
  );
}

// ── Summary bar ───────────────────────────────────────────────────────────────

function SummaryBar({ result }: { result: OracleEvaluationResult }) {
  return (
    <div className={styles.summaryBar}>
      <span className={styles.summaryItem}>
        <strong>Total scenarios:</strong> {result.total_scenarios}
      </span>
      <span className={styles.summaryItem}>
        <strong>Evaluated:</strong> {result.evaluated_scenarios}
      </span>
      <span className={styles.summaryItem} style={{ color: "#16a34a" }}>
        <strong>PASS:</strong> {result.pass_count}
      </span>
      <span className={styles.summaryItem} style={{ color: "#dc2626" }}>
        <strong>FAIL:</strong> {result.fail_count}
      </span>
      <span className={styles.summaryItem} style={{ color: "#9333ea" }}>
        <strong>No oracle:</strong> {result.no_oracle_count}
      </span>
      <span className={styles.summaryItem} style={{ color: "#d97706" }}>
        <strong>Weak only:</strong> {result.weak_only_count}
      </span>
      {result.publish_blocked && (
        <span className={styles.blockingBadge}>
          ⛔ P0 BLOCKED ({result.p0_blocked_count})
        </span>
      )}
    </div>
  );
}

// ── Scenario oracle card ──────────────────────────────────────────────────────

function ScenarioOracleCard({ scenario }: { scenario: ScenarioOracleResult }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`${styles.scenarioCard} ${scenario.blocking ? styles.blocking : ""}`}
    >
      <div
        className={styles.scenarioHeader}
        onClick={() => setExpanded((e) => !e)}
        style={{ cursor: "pointer" }}
      >
        <span className={styles.scenarioId}>{scenario.scenario_id}</span>
        <VerdictBadge verdict={scenario.oracle_verdict} />
        {scenario.is_p0 && <span className={styles.p0Tag}>P0</span>}
        {scenario.blocking && <span className={styles.blockingTag}>⛔ BLOCKING</span>}
        <span className={styles.oracleCounts}>
          {scenario.oracle_count} oracle{scenario.oracle_count !== 1 ? "s" : ""}
          {" · "}
          <span style={{ color: "#16a34a" }}>{scenario.pass_count} pass</span>
          {" · "}
          <span style={{ color: "#dc2626" }}>{scenario.fail_count} fail</span>
        </span>
        <span className={styles.expandIcon}>{expanded ? "▾" : "▸"}</span>
      </div>

      {expanded && (
        <div className={styles.oracleChecks}>
          {scenario.oracle_checks.length === 0 ? (
            <p className={styles.noOracle}>
              No oracle contracts defined for this scenario.
              {scenario.is_p0 && " This is a P0 scenario — an oracle is required to publish."}
            </p>
          ) : (
            scenario.oracle_checks.map((check, idx) => (
              <div key={idx} className={styles.oracleCheck}>
                <span className={styles.checkId}>{check.oracle_id}</span>
                <VerdictBadge verdict={check.verdict} small />
                <StrengthBadge strength={check.strength} />
                <span className={styles.checkType}>{check.oracle_type}</span>
                <span className={styles.checkDesc}>{check.description}</span>
                {check.error && (
                  <span className={styles.checkError} title={check.error}>
                    ⚠ {check.error}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Weak assertion file card ──────────────────────────────────────────────────

function WeakFileCard({ analysis }: { analysis: FileAssertionAnalysis }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`${styles.weakFileCard} ${analysis.has_weak_tests ? styles.hasWeak : ""}`}
    >
      <div
        className={styles.weakFileHeader}
        onClick={() => setExpanded((e) => !e)}
        style={{ cursor: "pointer" }}
      >
        <span className={styles.fileName}>{analysis.file_name}</span>
        <span className={styles.weakCounts}>
          <span style={{ color: "#16a34a" }}>{analysis.strong_tests} strong</span>
          {" · "}
          <span style={{ color: "#d97706" }}>{analysis.weak_tests} weak</span>
          {" · "}
          <span style={{ color: "#9333ea" }}>{analysis.trivial_tests} trivial</span>
          {" · "}
          <span style={{ color: "#6b7280" }}>{analysis.no_assertion_tests} none</span>
        </span>
        <span className={styles.expandIcon}>{expanded ? "▾" : "▸"}</span>
      </div>

      {expanded && (
        <div className={styles.weakTests}>
          {analysis.test_results.filter((t) => t.is_weak).map((t, idx) => (
            <div key={idx} className={styles.weakTest}>
              <span className={styles.weakTestName}>
                {t.line_number ? `L${t.line_number}: ` : ""}
                {t.test_name}
              </span>
              <span
                className={styles.weakStrength}
                style={{ color: STRENGTH_COLORS[t.assertion_strength] ?? "#374151" }}
              >
                [{t.assertion_strength}]
              </span>
              {t.finding && (
                <span className={styles.weakFinding} title={t.finding}>
                  {t.finding}
                </span>
              )}
            </div>
          ))}
          {analysis.test_results.filter((t) => t.is_weak).length === 0 && (
            <p className={styles.allStrong}>All tests have strong assertions ✓</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type OracleDashboardProps = {
  runId: string;
  ticketId: number;
};

export default function OracleDashboard({ runId, ticketId }: OracleDashboardProps) {
  const queryClient = useQueryClient();

  // Load oracle evaluation results
  const { data: oracleData, isLoading: oracleLoading } = useQuery({
    queryKey: ["oracle-results", runId, ticketId],
    queryFn: () => QaUat.listOracleResults(runId, ticketId),
    retry: 1,
  });

  // Load weak assertion report
  const { data: weakData, isLoading: weakLoading } = useQuery({
    queryKey: ["weak-assertions", runId, ticketId],
    queryFn: () => QaUat.getWeakAssertions(runId, ticketId),
    retry: 1,
  });

  // On-demand evaluation mutation
  const evaluateMutation = useMutation({
    mutationFn: () =>
      QaUat.evaluateOracles({ run_id: runId, ticket_id: ticketId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["oracle-results", runId, ticketId] });
      queryClient.invalidateQueries({ queryKey: ["weak-assertions", runId, ticketId] });
    },
  });

  const oracleResult: OracleEvaluationResult | null =
    oracleData?.results?.[0] ?? null;
  const weakReport: WeakAssertionReport | null = weakData?.report ?? null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>Oracle Engine — Sprint 13</h3>
        <button
          className={styles.evaluateBtn}
          onClick={() => evaluateMutation.mutate()}
          disabled={evaluateMutation.isPending}
        >
          {evaluateMutation.isPending ? "Evaluando..." : "⚡ Evaluar oracles"}
        </button>
      </div>

      {evaluateMutation.isError && (
        <div className={styles.errorBanner}>
          Error al evaluar: {String(evaluateMutation.error)}
        </div>
      )}

      {/* Oracle evaluation results */}
      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Oracle Contracts</h4>
        {oracleLoading && <p className={styles.loading}>Cargando resultados oracle…</p>}
        {!oracleLoading && !oracleResult && (
          <p className={styles.empty}>
            No hay oracle_result.json para este run.
            Hacé click en "Evaluar oracles" para generar el reporte.
          </p>
        )}
        {oracleResult && (
          <>
            <SummaryBar result={oracleResult} />
            <div className={styles.scenarioList}>
              {oracleResult.scenario_results.map((sr) => (
                <ScenarioOracleCard key={sr.scenario_id} scenario={sr} />
              ))}
              {oracleResult.scenario_results.length === 0 && (
                <p className={styles.empty}>
                  Sin escenarios evaluados. El archivo oracle_contracts/ puede estar vacío.
                </p>
              )}
            </div>
          </>
        )}
      </section>

      {/* Weak assertion analysis */}
      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Weak Assertion Detector</h4>
        {weakLoading && <p className={styles.loading}>Analizando assertions…</p>}
        {!weakLoading && !weakReport && (
          <p className={styles.empty}>
            No hay weak_assertion_report.json para este run.
            El análisis se genera durante la ejecución del pipeline.
          </p>
        )}
        {weakReport && (
          <>
            <div className={styles.summaryBar}>
              <span className={styles.summaryItem}>
                <strong>Archivos:</strong> {weakReport.files_analyzed}
              </span>
              <span className={styles.summaryItem}>
                <strong>Tests totales:</strong> {weakReport.total_tests}
              </span>
              <span className={styles.summaryItem} style={{ color: "#16a34a" }}>
                <strong>Strong:</strong> {weakReport.strong_tests}
              </span>
              <span className={styles.summaryItem} style={{ color: "#d97706" }}>
                <strong>Weak:</strong> {weakReport.weak_tests}
              </span>
              <span className={styles.summaryItem} style={{ color: "#9333ea" }}>
                <strong>Trivial:</strong> {weakReport.trivial_tests}
              </span>
              <span className={styles.summaryItem} style={{ color: "#6b7280" }}>
                <strong>Sin assertions:</strong> {weakReport.no_assertion_tests}
              </span>
              {weakReport.publish_blocked && (
                <span className={styles.blockingBadge}>⛔ PUBLICACIÓN BLOQUEADA</span>
              )}
            </div>
            <div className={styles.fileList}>
              {weakReport.file_analyses.map((fa) => (
                <WeakFileCard key={fa.file_name} analysis={fa} />
              ))}
              {weakReport.file_analyses.length === 0 && (
                <p className={styles.empty}>No se analizaron archivos spec.</p>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

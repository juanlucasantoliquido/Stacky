/**
 * ConfidenceDashboard.tsx — Sprint 14: Test Confidence + Data Lineage
 *
 * Shows per-scenario confidence scores and the data lineage audit trail.
 *
 * Features:
 *  - Confidence level (HIGH/MEDIUM/LOW) per scenario with score bar
 *  - Per-factor breakdown showing what contributed/penalized each score
 *  - Publish gate indicator: blocked scenarios highlighted in red
 *  - Data lineage table: field → source → script → cleaned_up
 *  - On-demand re-score and lineage rebuild buttons
 *
 * Displayed in DossierPanel when:
 *  - `stages.test_confidence.publish_blocked === true`
 *  - OR `stages.test_confidence.low_count > 0`
 *
 * Props:
 *   runId    — pipeline run_id
 *   ticketId — ADO ticket ID
 *
 * Security:
 *   - Read-only display — no DB or seed operations triggered.
 *   - Score and lineage re-builds are read-only operations.
 */
import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import type {
  ConfidenceReport,
  ConfidenceScore,
  DataLineageResult,
  LineageEntry,
} from "../api/endpoints";
import styles from "./ConfidenceDashboard.module.css";

// ── Level colors ──────────────────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, string> = {
  HIGH:   "#16a34a",
  MEDIUM: "#d97706",
  LOW:    "#dc2626",
};

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ score, level }: { score: number; level: string }) {
  const color = LEVEL_COLORS[level] ?? "#6b7280";
  return (
    <div className={styles.scoreBarWrap} title={`Score: ${score}/100`}>
      <div
        className={styles.scoreBarFill}
        style={{ width: `${Math.max(0, Math.min(100, score))}%`, background: color }}
      />
      <span className={styles.scoreBarLabel}>{score}</span>
    </div>
  );
}

// ── Level badge ───────────────────────────────────────────────────────────────

function LevelBadge({ level }: { level: string }) {
  return (
    <span
      className={styles.levelBadge}
      style={{ background: LEVEL_COLORS[level] ?? "#374151" }}
    >
      {level}
    </span>
  );
}

// ── Source badge ──────────────────────────────────────────────────────────────

const SOURCE_COLORS: Record<string, string> = {
  SEEDED:        "#2563eb",
  USER_SUPPLIED: "#7c3aed",
  FIXTURE:       "#0891b2",
  DISCOVERED:    "#059669",
  ENVIRONMENT:   "#6b7280",
  UNKNOWN:       "#374151",
};

function SourceBadge({ source }: { source: string }) {
  return (
    <span
      className={styles.sourceBadge}
      style={{ background: SOURCE_COLORS[source] ?? "#374151" }}
    >
      {source}
    </span>
  );
}

// ── Scenario confidence card ──────────────────────────────────────────────────

function ScenarioConfidenceCard({ cs }: { cs: ConfidenceScore }) {
  const [expanded, setExpanded] = useState(false);
  const positiveFactors = cs.factors.filter((f) => f.delta > 0);
  const negativeFactors = cs.factors.filter((f) => f.delta < 0);

  return (
    <div
      className={`${styles.scenarioCard} ${cs.publish_blocked ? styles.blocked : ""}`}
    >
      <div
        className={styles.scenarioHeader}
        onClick={() => setExpanded((e) => !e)}
        style={{ cursor: "pointer" }}
      >
        <span className={styles.scenarioId}>{cs.scenario_id}</span>
        <LevelBadge level={cs.level} />
        {cs.is_p0 && <span className={styles.p0Tag}>P0</span>}
        {cs.publish_blocked && <span className={styles.blockTag}>⛔ BLOQUEADO</span>}
        <ScoreBar score={cs.score} level={cs.level} />
        <span className={styles.expandIcon}>{expanded ? "▾" : "▸"}</span>
      </div>

      {expanded && (
        <div className={styles.factorsList}>
          {positiveFactors.length > 0 && (
            <div className={styles.factorGroup}>
              <span className={styles.factorGroupLabel} style={{ color: "#4ade80" }}>
                ✓ Positivos
              </span>
              {positiveFactors.map((f, i) => (
                <div key={i} className={styles.factorRow}>
                  <span className={styles.factorDelta} style={{ color: "#4ade80" }}>
                    +{f.delta}
                  </span>
                  <span className={styles.factorName}>{f.name}</span>
                  <span className={styles.factorReason}>{f.reason}</span>
                </div>
              ))}
            </div>
          )}
          {negativeFactors.length > 0 && (
            <div className={styles.factorGroup}>
              <span className={styles.factorGroupLabel} style={{ color: "#fca5a5" }}>
                ✗ Penalizaciones
              </span>
              {negativeFactors.map((f, i) => (
                <div key={i} className={styles.factorRow}>
                  <span className={styles.factorDelta} style={{ color: "#fca5a5" }}>
                    {f.delta}
                  </span>
                  <span className={styles.factorName}>{f.name}</span>
                  <span className={styles.factorReason}>{f.reason}</span>
                </div>
              ))}
            </div>
          )}
          {cs.factors.length === 0 && (
            <p className={styles.noFactors}>Sin factores registrados.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Lineage table ─────────────────────────────────────────────────────────────

function LineageTable({ entries }: { entries: LineageEntry[] }) {
  if (entries.length === 0) {
    return <p className={styles.empty}>Sin entradas de lineage.</p>;
  }

  return (
    <table className={styles.lineageTable}>
      <thead>
        <tr>
          <th>Campo</th>
          <th>Valor</th>
          <th>Origen</th>
          <th>Escenario</th>
          <th>Script</th>
          <th>Limpiado</th>
          <th>Nota</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={i} className={e.cleaned_up ? styles.cleanedRow : ""}>
            <td className={styles.fieldCell}>{e.field}</td>
            <td className={styles.valueCell}>{e.value ?? <em className={styles.redacted}>[redactado]</em>}</td>
            <td><SourceBadge source={e.source} /></td>
            <td className={styles.scenarioCell}>{e.scenario_id}</td>
            <td className={styles.scriptCell}>{e.seed_script ?? "—"}</td>
            <td className={styles.cleanedCell}>
              {e.cleaned_up
                ? <span className={styles.cleanedYes}>✓</span>
                : <span className={styles.cleanedNo}>✗</span>}
            </td>
            <td className={styles.noteCell}>{e.origin_note ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Summary bar ───────────────────────────────────────────────────────────────

function ConfidenceSummaryBar({ report }: { report: ConfidenceReport }) {
  return (
    <div className={styles.summaryBar}>
      <span className={styles.summaryItem}>
        <strong>Escenarios:</strong> {report.total_scenarios}
      </span>
      <span className={styles.summaryItem} style={{ color: "#16a34a" }}>
        <strong>HIGH:</strong> {report.high_count}
      </span>
      <span className={styles.summaryItem} style={{ color: "#d97706" }}>
        <strong>MEDIUM:</strong> {report.medium_count}
      </span>
      <span className={styles.summaryItem} style={{ color: "#dc2626" }}>
        <strong>LOW:</strong> {report.low_count}
      </span>
      <span className={styles.summaryItem}>
        <strong>Gate mínimo:</strong> {report.min_confidence}
      </span>
      {report.publish_blocked && (
        <span className={styles.blockingBadge}>
          ⛔ PUBLICACIÓN BLOQUEADA ({report.blocked_count} escenarios)
        </span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type ConfidenceDashboardProps = {
  runId: string;
  ticketId: number;
};

export default function ConfidenceDashboard({ runId, ticketId }: ConfidenceDashboardProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"confidence" | "lineage">("confidence");

  // Load confidence report
  const { data: confData, isLoading: confLoading } = useQuery({
    queryKey: ["confidence-report", runId, ticketId],
    queryFn: () => QaUat.getConfidenceReport(runId, ticketId),
    retry: 1,
  });

  // Load data lineage
  const { data: lineageData, isLoading: lineageLoading } = useQuery({
    queryKey: ["data-lineage", runId, ticketId],
    queryFn: () => QaUat.getDataLineage(runId, ticketId),
    retry: 1,
  });

  // Re-score mutation
  const scoreMutation = useMutation({
    mutationFn: () => QaUat.scoreConfidence({ run_id: runId, ticket_id: ticketId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["confidence-report", runId, ticketId] });
    },
  });

  // Build lineage mutation
  const lineageMutation = useMutation({
    mutationFn: () => QaUat.buildDataLineage({ run_id: runId, ticket_id: ticketId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-lineage", runId, ticketId] });
    },
  });

  const report: ConfidenceReport | null = confData?.report ?? null;
  const lineage: DataLineageResult | null = lineageData?.lineage ?? null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>Test Confidence — Sprint 14</h3>
        <div className={styles.headerActions}>
          <button
            className={styles.actionBtn}
            onClick={() => scoreMutation.mutate()}
            disabled={scoreMutation.isPending}
          >
            {scoreMutation.isPending ? "Calculando..." : "⚡ Re-score"}
          </button>
          <button
            className={styles.actionBtn}
            onClick={() => lineageMutation.mutate()}
            disabled={lineageMutation.isPending}
          >
            {lineageMutation.isPending ? "Construyendo..." : "🔗 Build lineage"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "confidence" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("confidence")}
        >
          Confidence
        </button>
        <button
          className={`${styles.tab} ${activeTab === "lineage" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("lineage")}
        >
          Data Lineage
          {lineage && ` (${lineage.total_entries})`}
        </button>
      </div>

      {/* Confidence tab */}
      {activeTab === "confidence" && (
        <div className={styles.tabContent}>
          {confLoading && <p className={styles.loading}>Cargando reporte…</p>}
          {!confLoading && !report && (
            <p className={styles.empty}>
              Sin confidence_report.json. Hacé click en "Re-score" para generarlo.
            </p>
          )}
          {report && (
            <>
              <ConfidenceSummaryBar report={report} />
              <div className={styles.scenarioList}>
                {report.scenario_scores.map((cs) => (
                  <ScenarioConfidenceCard key={cs.scenario_id} cs={cs} />
                ))}
                {report.scenario_scores.length === 0 && (
                  <p className={styles.empty}>Sin escenarios puntuados.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Lineage tab */}
      {activeTab === "lineage" && (
        <div className={styles.tabContent}>
          {lineageLoading && <p className={styles.loading}>Cargando lineage…</p>}
          {!lineageLoading && !lineage && (
            <p className={styles.empty}>
              Sin data_lineage.json. Hacé click en "Build lineage" para generarlo.
            </p>
          )}
          {lineage && (
            <>
              <div className={styles.summaryBar}>
                <span className={styles.summaryItem}>
                  <strong>Total entradas:</strong> {lineage.total_entries}
                </span>
                <span className={styles.summaryItem} style={{ color: "#2563eb" }}>
                  <strong>Seeded:</strong> {lineage.seeded_count}
                </span>
                <span className={styles.summaryItem} style={{ color: "#7c3aed" }}>
                  <strong>User supplied:</strong> {lineage.user_supplied_count}
                </span>
                <span className={styles.summaryItem} style={{ color: "#0891b2" }}>
                  <strong>Fixture:</strong> {lineage.fixture_count}
                </span>
                <span className={styles.summaryItem} style={{ color: "#059669" }}>
                  <strong>Discovered:</strong> {lineage.discovered_count}
                </span>
              </div>
              <div className={styles.lineageWrap}>
                <LineageTable entries={lineage.entries} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PmApi,
  type PmAiModel,
  type PmAiModelsReport,
  type PmAiUsageBreakdown,
  type PmAiUsageReport,
  type PmComment,
  type PmEvalReport,
  type PmRecommendation,
  type PmRecommendationRunResult,
  type PmRiskItem,
  type PmSprintKpis,
  type PmSprintSnapshotRow,
} from "../api/pm";
import WeeklyDigestCard from "../components/WeeklyDigestCard";
import { useWorkbench } from "../store/workbench";
import {
  formatDate,
  formatTime,
  formatDateTime,
  formatDuration,
  formatCostUsd,
  formatTokens,
  formatPercent,
} from "../services/format";
import styles from "./PMCommandCenter.module.css";

type SeverityFilter = "ALL" | "HIGH" | "MEDIUM" | "LOW" | "CRITICAL";

function healthClass(kpis: PmSprintKpis | null): string {
  if (!kpis || kpis.total_items === 0) return styles.healthGray;
  const completion = kpis.completion_rate_pct;
  if (kpis.blocked_items > 0 && (kpis.days_remaining ?? 99) <= 2) return styles.healthRed;
  if (completion >= 75) return styles.healthGreen;
  if (completion >= 50) return styles.healthYellow;
  return styles.healthRed;
}

function healthLabel(kpis: PmSprintKpis | null): string {
  if (!kpis || kpis.total_items === 0) return "Sin datos";
  const cls = healthClass(kpis);
  if (cls === styles.healthGreen) return "Saludable";
  if (cls === styles.healthYellow) return "Atención";
  if (cls === styles.healthRed) return "En riesgo";
  return "Sin datos";
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
}

function KpiCard({ label, value, sub }: KpiCardProps) {
  return (
    <div className={styles.kpiCard}>
      <div className={styles.kpiLabel}>{label}</div>
      <div className={styles.kpiValue}>{value}</div>
      {sub && <div className={styles.kpiSub}>{sub}</div>}
    </div>
  );
}

// ── Sprint Health Card ────────────────────────────────────────────────────────

interface SprintHealthCardProps {
  snapshot: PmSprintSnapshotRow | null;
  capturedAt: string | null;
}

function SprintHealthCard({ snapshot, capturedAt }: SprintHealthCardProps) {
  const kpis = snapshot?.snapshot?.kpis ?? null;
  const iteration = snapshot?.snapshot?.iteration ?? null;

  return (
    <div className={styles.sprintCard}>
      <div className={styles.sprintTop}>
        <h2 className={styles.sprintName}>{snapshot?.sprint_name ?? "Sin sprint sincronizado"}</h2>
        <span className={styles.sprintMeta}>
          {formatDate(iteration?.start_date ?? snapshot?.start_date ?? null)}
          {" → "}
          {formatDate(iteration?.end_date ?? snapshot?.end_date ?? null)}
        </span>
        <span className={`${styles.healthPill} ${healthClass(kpis)}`}>
          {healthLabel(kpis)}
        </span>
        {capturedAt && (
          <span className={styles.sprintMeta}>
            Último sync: {formatDateTime(capturedAt)}
          </span>
        )}
      </div>

      <div className={styles.kpiGrid}>
        <KpiCard
          label="Completion"
          value={kpis ? formatPercent(kpis.completion_rate_pct) : "—"}
          sub={
            kpis && kpis.committed_story_points > 0
              ? `${kpis.completed_story_points}/${kpis.committed_story_points} pts`
              : kpis
                ? `${kpis.done_items}/${kpis.total_items} items`
                : undefined
          }
        />
        <KpiCard
          label="Total items"
          value={kpis?.total_items ?? "—"}
          sub={
            kpis
              ? `${kpis.active_items} activos · ${kpis.blocked_items} bloqueados`
              : undefined
          }
        />
        <KpiCard
          label="Bugs"
          value={kpis ? `${kpis.bug_count}` : "—"}
          sub={kpis ? `${formatPercent(kpis.bug_rate_pct, 1)} del sprint` : undefined}
        />
        <KpiCard
          label="Días restantes"
          value={kpis?.days_remaining ?? "—"}
        />
        <KpiCard
          label="Aging promedio"
          value={kpis?.avg_aging_days != null ? `${kpis.avg_aging_days.toFixed(1)}d` : "—"}
        />
        <KpiCard
          label="Cycle time"
          value={kpis?.avg_cycle_time_days != null ? `${kpis.avg_cycle_time_days.toFixed(1)}d` : "—"}
          sub="promedio del sprint"
        />
        <KpiCard
          label="Sin estimación"
          value={kpis?.items_without_estimation ?? "—"}
        />
        <KpiCard
          label="Sin owner"
          value={kpis?.items_without_owner ?? "—"}
        />
      </div>

      {kpis && kpis.data_quality_warnings.length > 0 && (
        <ul className={styles.dqList}>
          {kpis.data_quality_warnings.map((w, i) => (
            <li key={`${w.warning_type}-${i}`} className={styles.dqItem}>
              <strong>{w.warning_type}</strong> — {w.impact}
              {" "}({w.count}, {w.percentage}%)
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Risk Feed ────────────────────────────────────────────────────────────────

interface RiskFeedProps {
  risks: PmRiskItem[];
  onAcknowledge: (riskId: string) => void;
  ackInFlight: string | null;
}

function RiskFeed({ risks, onAcknowledge, ackInFlight }: RiskFeedProps) {
  if (risks.length === 0) {
    return <div className={styles.empty}>Sin riesgos detectados para los filtros actuales.</div>;
  }
  return (
    <div className={styles.riskList}>
      {risks.map((r) => {
        const sevClass = styles[`severity${r.severity}`] ?? "";
        return (
          <div
            key={r.risk_id}
            className={`${styles.riskItem} ${sevClass} ${r.acknowledged ? styles.ackd : ""}`}
          >
            <div className={styles.riskHeader}>
              <span className={`${styles.severityBadge} ${sevClass}`}>{r.severity}</span>
              <span className={styles.riskCategory}>{r.category}</span>
              {r.rule && <span className={styles.riskRule}>{r.rule}</span>}
              {r.acknowledged ? (
                <span className={styles.ackedMark}>
                  ✓ acknowledged por {r.acknowledged_by ?? "?"} ({formatDateTime(r.acknowledged_at)})
                </span>
              ) : (
                <button
                  className={styles.btnAck}
                  onClick={() => onAcknowledge(r.risk_id)}
                  disabled={ackInFlight === r.risk_id}
                >
                  {ackInFlight === r.risk_id ? "..." : "Acknowledge"}
                </button>
              )}
            </div>
            <div className={styles.riskDescription}>{r.description ?? "(sin descripción)"}</div>
            <div className={styles.riskMeta}>
              <span>ID: {r.risk_id}</span>
              {r.affected_items.length > 0 && (
                <span className={styles.riskItems}>
                  Items: {r.affected_items.slice(0, 8).join(", ")}
                  {r.affected_items.length > 8 ? ` (+${r.affected_items.length - 8} más)` : ""}
                </span>
              )}
              <span>Detectado: {formatDateTime(r.detected_at)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── AI Usage Panel ────────────────────────────────────────────────────────────

interface AIUsagePanelProps {
  report: PmAiUsageReport | null;
  windowHours: number;
  onWindowChange: (h: number) => void;
  loading: boolean;
}

function AIUsagePanel({ report, windowHours, onWindowChange, loading }: AIUsagePanelProps) {
  const totals = report?.totals;
  const byModel = report?.by_model ?? {};
  const byAgent = report?.by_agent ?? {};
  const recent = report?.recent_calls ?? [];

  const breakdownRow = (key: string, data: PmAiUsageBreakdown) => (
    <tr key={key}>
      <td className={styles.mono}>{key}</td>
      <td className={styles.numeric}>{data.calls}</td>
      <td className={styles.numeric}>{formatTokens(data.tokens_in)}</td>
      <td className={styles.numeric}>{formatTokens(data.tokens_out)}</td>
      <td className={styles.numeric}>{formatCostUsd(data.cost_usd)}</td>
      <td className={styles.numeric}>
        {data.calls > 0 ? formatPercent((data.success / data.calls) * 100) : "—"}
      </td>
    </tr>
  );

  return (
    <section className={styles.aiPanel}>
      <div className={styles.aiHeader}>
        <h3 className={styles.aiTitle}>🤖 AI Usage Tracking</h3>
        <span className={styles.advisoryBadge}>advisory_only</span>
        <span className={styles.aiWindow}>
          Ventana: últimas {windowHours}h
          {report?.window_start && ` · desde ${formatDateTime(report.window_start)}`}
        </span>
        <select
          className={styles.aiSelector}
          value={windowHours}
          onChange={(e) => onWindowChange(parseInt(e.target.value, 10))}
        >
          <option value={1}>1h</option>
          <option value={24}>24h</option>
          <option value={72}>3d</option>
          <option value={168}>7d</option>
        </select>
      </div>

      <div className={styles.aiTotalsGrid}>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Costo USD</div>
          <div className={styles.aiKpiValue}>{loading ? "..." : formatCostUsd(totals?.cost_usd ?? 0)}</div>
          <div className={styles.aiKpiSub}>{totals?.calls ?? 0} llamadas</div>
        </div>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Tokens in</div>
          <div className={styles.aiKpiValue}>{formatTokens(totals?.tokens_in ?? 0)}</div>
        </div>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Tokens out</div>
          <div className={styles.aiKpiValue}>{formatTokens(totals?.tokens_out ?? 0)}</div>
        </div>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Total tokens</div>
          <div className={styles.aiKpiValue}>{formatTokens(totals?.tokens_total ?? 0)}</div>
        </div>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Success rate</div>
          <div className={styles.aiKpiValue}>
            {totals && totals.calls > 0 ? formatPercent(totals.success_rate_pct) : "—"}
          </div>
          <div className={styles.aiKpiSub}>
            {totals?.success ?? 0}/{totals?.calls ?? 0}
          </div>
        </div>
        <div className={styles.aiKpi}>
          <div className={styles.aiKpiLabel}>Latencia avg</div>
          <div className={styles.aiKpiValue}>
            {totals && totals.calls > 0 ? formatDuration(totals.latency_ms_avg) : "—"}
          </div>
        </div>
      </div>

      {Object.keys(byModel).length > 0 && (
        <div className={styles.aiBreakdownSection}>
          <h4 className={styles.aiBreakdownTitle}>Por modelo</h4>
          <table className={styles.aiBreakdownTable}>
            <thead>
              <tr>
                <th>Modelo</th>
                <th style={{ textAlign: "right" }}>Calls</th>
                <th style={{ textAlign: "right" }}>Tokens in</th>
                <th style={{ textAlign: "right" }}>Tokens out</th>
                <th style={{ textAlign: "right" }}>Costo</th>
                <th style={{ textAlign: "right" }}>Success</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byModel).map(([k, v]) => breakdownRow(k, v))}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(byAgent).length > 0 && (
        <div className={styles.aiBreakdownSection}>
          <h4 className={styles.aiBreakdownTitle}>Por agente</h4>
          <table className={styles.aiBreakdownTable}>
            <thead>
              <tr>
                <th>Agente</th>
                <th style={{ textAlign: "right" }}>Calls</th>
                <th style={{ textAlign: "right" }}>Tokens in</th>
                <th style={{ textAlign: "right" }}>Tokens out</th>
                <th style={{ textAlign: "right" }}>Costo</th>
                <th style={{ textAlign: "right" }}>Success</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byAgent).map(([k, v]) => breakdownRow(k, v))}
            </tbody>
          </table>
        </div>
      )}

      {recent.length > 0 && (
        <div className={styles.aiBreakdownSection}>
          <h4 className={styles.aiBreakdownTitle}>Últimas {recent.length} llamadas</h4>
          <div className={styles.aiRecent}>
            {recent.map((r) => (
              <div
                key={r.id}
                className={`${styles.aiRecentRow} ${!r.success ? styles.failed : ""}`}
              >
                <span className={styles.aiTimestamp}>
                  {formatTime(r.timestamp)}
                </span>
                <span className={styles.aiAgent}>{r.agent_kind}</span>
                <span className={styles.aiModel}>{r.model}</span>
                <span className={styles.aiTokens}>
                  {formatTokens(r.tokens_in)}↓ {formatTokens(r.tokens_out)}↑
                </span>
                <span className={styles.aiCost}>{formatCostUsd(r.cost_usd)}</span>
                {!r.success && <span className={styles.aiErr}>{r.error ?? "error"}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && (totals?.calls ?? 0) === 0 && (
        <div className={styles.empty}>
          Aún no hay llamadas IA registradas en esta ventana. Cuando se ejecuten
          análisis de sentiment o recommendations, aparecerán acá con su consumo de tokens
          y costo USD para que puedas ajustar el presupuesto.
        </div>
      )}
    </section>
  );
}

// ── AI Control Panel (F2-R) ───────────────────────────────────────────────────

type EvalComponent = "comment_sentiment" | "recommendation_engine";

interface AIControlPanelProps {
  sentimentReport: PmEvalReport | null;
  recReport: PmEvalReport | null;
  onRunEvals: (component: EvalComponent) => void;
  onGenerateRecs: (forceUnsafe: boolean) => void;
  runningEvals: EvalComponent | null;
  generatingRecs: boolean;
  lastRecRun: PmRecommendationRunResult | null;
  modelsReport: PmAiModelsReport | null;
  modelsLoading: boolean;
  selectedModel: string;
  onModelChange: (model: string) => void;
}

function gateBadge(report: PmEvalReport | null): { label: string; cls: string } {
  if (!report) return { label: "no corrida", cls: styles.gateUnknown };
  return report.gate_passed
    ? { label: "passed", cls: styles.gatePass }
    : { label: "failed", cls: styles.gateFail };
}

function fmtPricing(m: PmAiModel): string {
  if (!m.pricing_per_1m_usd) return "";
  const p = m.pricing_per_1m_usd;
  if (p.input === 0 && p.output === 0) return " (mock)";
  return ` ($${p.input.toFixed(2)}/${p.output.toFixed(2)} per 1M)`;
}

function AIControlPanel({
  sentimentReport, recReport,
  onRunEvals, onGenerateRecs, runningEvals, generatingRecs, lastRecRun,
  modelsReport, modelsLoading, selectedModel, onModelChange,
}: AIControlPanelProps) {
  const sentimentBadge = gateBadge(sentimentReport);
  const recBadge = gateBadge(recReport);

  const recGateFailed = recReport ? !recReport.gate_passed : false;
  const models = modelsReport?.models ?? [];
  const backendLabel = modelsReport?.backend ?? "?";
  const modelsError = modelsReport?.error ?? null;

  return (
    <section className={styles.ctrlPanel}>
      <div className={styles.ctrlHeader}>
        <h3 className={styles.ctrlTitle}>🧪 AI Components · Evals & Run</h3>
        <span className={styles.advisoryBadge}>advisory_only</span>
        <span className={styles.ctrlSubtitle}>
          Los componentes IA solo se habilitan si pasan sus eval fixtures
        </span>
      </div>

      <div className={styles.modelSelectorBar}>
        <span className={styles.filterLabel}>Modelo:</span>
        <select
          className={styles.modelSelect}
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={modelsLoading || models.length === 0}
          title="Modelo usado para evals, sentiment y recommendations"
        >
          {models.length === 0 && <option value="">Cargando modelos...</option>}
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}{m.is_premium ? " ⭐" : ""}{m.preview ? " (preview)" : ""}{fmtPricing(m)}
            </option>
          ))}
        </select>
        <span className={styles.modelBackend}>backend: {backendLabel}</span>
        {modelsError && (
          <span className={styles.modelWarning} title={modelsError}>
            ⚠ catálogo offline (usando fallback)
          </span>
        )}
      </div>

      <div className={styles.gateGrid}>
        {/* Sentiment column */}
        <div className={styles.gateCard}>
          <div className={styles.gateCardHeader}>
            <span className={styles.gateName}>comment_sentiment</span>
            <span className={`${styles.gateStatus} ${sentimentBadge.cls}`}>
              {sentimentBadge.label}
            </span>
          </div>
          {sentimentReport && (
            <div className={styles.gateMetrics}>
              <span>{sentimentReport.passed}/{sentimentReport.total} fixtures</span>
              <span>{formatCostUsd(sentimentReport.cost_usd_total)}</span>
              <span>{sentimentReport.tokens_in_total + sentimentReport.tokens_out_total} tokens</span>
              <span>{sentimentReport.duration_ms}ms</span>
            </div>
          )}
          <div className={styles.gateActions}>
            <button
              className={styles.gateBtn}
              onClick={() => onRunEvals("comment_sentiment")}
              disabled={runningEvals !== null}
            >
              {runningEvals === "comment_sentiment" ? "Corriendo..." : "Run sentiment evals"}
            </button>
          </div>
          {sentimentReport && !sentimentReport.gate_passed && (
            <div className={styles.gateFailures}>
              {sentimentReport.fixtures
                .filter(f => !f.passed)
                .slice(0, 3)
                .map(f => `• ${f.fixture_id}: ${f.failures.slice(0, 2).join(", ")}`)
                .join("\n")}
            </div>
          )}
        </div>

        {/* Recommendation column */}
        <div className={styles.gateCard}>
          <div className={styles.gateCardHeader}>
            <span className={styles.gateName}>recommendation_engine</span>
            <span className={`${styles.gateStatus} ${recBadge.cls}`}>
              {recBadge.label}
            </span>
          </div>
          {recReport && (
            <div className={styles.gateMetrics}>
              <span>{recReport.passed}/{recReport.total} fixtures</span>
              <span>{formatCostUsd(recReport.cost_usd_total)}</span>
              <span>{recReport.tokens_in_total + recReport.tokens_out_total} tokens</span>
              <span>{recReport.duration_ms}ms</span>
            </div>
          )}
          <div className={styles.gateActions}>
            <button
              className={styles.gateBtn}
              onClick={() => onRunEvals("recommendation_engine")}
              disabled={runningEvals !== null}
            >
              {runningEvals === "recommendation_engine" ? "Corriendo..." : "Run rec evals"}
            </button>
            <button
              className={styles.gateBtn}
              onClick={() => onGenerateRecs(false)}
              disabled={generatingRecs}
              title={recGateFailed ? "El eval gate no pasó — se bloquea por default" : ""}
            >
              {generatingRecs ? "Generando..." : "Generate recommendations"}
            </button>
            {recGateFailed && (
              <button
                className={`${styles.gateBtn} ${styles.danger}`}
                onClick={() => onGenerateRecs(true)}
                disabled={generatingRecs}
                title="Bypassa el gate (solo para debug)"
              >
                Force unsafe
              </button>
            )}
          </div>
        </div>
      </div>

      {lastRecRun && (
        <div className={styles.gateMetrics} style={{ marginTop: 8 }}>
          <span>Última generación: {lastRecRun.generated} OK, {lastRecRun.rejected} rechazadas</span>
          <span>{formatCostUsd(lastRecRun.cost_usd)} · {lastRecRun.tokens_in + lastRecRun.tokens_out} tokens</span>
          <span>modelo: {lastRecRun.model}</span>
          {lastRecRun.rejected > 0 && (
            <span style={{ color: "#fde68a" }}>
              motivos: {lastRecRun.rejected_reasons.slice(0, 3).join(", ")}
            </span>
          )}
        </div>
      )}
    </section>
  );
}

// ── Recommendation Feed ───────────────────────────────────────────────────────

interface RecommendationFeedProps {
  recommendations: PmRecommendation[];
  onAcknowledge: (recId: string) => void;
  ackInFlight: string | null;
}

function RecommendationFeed({ recommendations, onAcknowledge, ackInFlight }: RecommendationFeedProps) {
  if (recommendations.length === 0) {
    return (
      <div className={styles.empty}>
        Aún no hay recomendaciones IA generadas. Corré los evals de
        recommendation_engine y después <strong>Generate recommendations</strong>.
      </div>
    );
  }
  return (
    <div className={styles.recList}>
      {recommendations.map((r) => {
        const prioClass = styles[`priority${r.priority}`] ?? "";
        return (
          <div
            key={r.rec_id}
            className={`${styles.recItem} ${prioClass} ${r.acknowledged ? styles.ackd : ""}`}
          >
            <div className={styles.recHeader}>
              <span className={`${styles.priorityBadge} ${prioClass}`}>{r.priority}</span>
              <span className={styles.recCategory}>{r.category}</span>
              <span className={styles.recConfidence}>
                conf {formatPercent(r.confidence * 100)}
              </span>
              {r.acknowledged ? (
                <span className={styles.ackedMark}>
                  ✓ ack {r.acknowledged_by} ({formatDateTime(r.acknowledged_at)})
                </span>
              ) : (
                <button
                  className={styles.btnAck}
                  onClick={() => onAcknowledge(r.rec_id)}
                  disabled={ackInFlight === r.rec_id}
                >
                  {ackInFlight === r.rec_id ? "..." : "Acknowledge"}
                </button>
              )}
            </div>
            <div className={styles.recAction}>{r.action}</div>
            {r.rationale && <div className={styles.recRationale}>{r.rationale}</div>}
            <div className={styles.recMeta}>
              <span>ID: {r.rec_id}</span>
              <span>modelo: {r.model}</span>
              <span>generado: {formatDateTime(r.generated_at)}</span>
              <span className={styles.advisoryBadge}>
                advisory · publish_recommended: {r.publish_recommended ? "true" : "false"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Comments Explorer (F2-S UI) ───────────────────────────────────────────────

function sentimentClass(label: string | null): string {
  switch ((label || "").toLowerCase()) {
    case "positive": return styles.sentimentPositive;
    case "negative": return styles.sentimentNegative;
    case "blocking": return styles.sentimentBlocking;
    case "neutral":  return styles.sentimentNeutral;
    default:         return styles.sentimentUnanalyzed;
  }
}

function stripHashMarker(text: string | null): string {
  if (!text) return "";
  const idx = text.lastIndexOf("\n[hash:");
  return idx === -1 ? text : text.slice(0, idx);
}

interface CommentsExplorerProps {
  adoId: number | null;
  onAdoIdChange: (id: number | null) => void;
  comments: PmComment[];
  loading: boolean;
  onIndex: () => void;
  onAnalyze: (forceUnsafe: boolean) => void;
  indexing: boolean;
  analyzing: boolean;
  lastIndex: { inserted: number; skipped_duplicates: number; total_fetched: number } | null;
  lastAnalyze: { analyzed: number; failures: number; gate_passed: boolean; cost_usd: number } | null;
}

function CommentsExplorer({
  adoId, onAdoIdChange, comments, loading,
  onIndex, onAnalyze, indexing, analyzing,
  lastIndex, lastAnalyze,
}: CommentsExplorerProps) {
  const unanalyzedCount = comments.filter(c => !c.ai_analyzed).length;
  const sentimentGateFailed = lastAnalyze ? !lastAnalyze.gate_passed : false;

  return (
    <section className={styles.commentsPanel}>
      <h3 className={styles.sectionTitle}>
        💬 Comentarios de Work Item
        {comments.length > 0 && ` (${comments.length})`}
      </h3>

      <div className={styles.commentsToolbar}>
        <span className={styles.filterLabel}>ADO ID:</span>
        <input
          type="number"
          className={styles.commentsInput}
          value={adoId ?? ""}
          onChange={(e) => {
            const v = e.target.value.trim();
            onAdoIdChange(v ? parseInt(v, 10) : null);
          }}
          placeholder="ej: 12345"
          min={1}
        />
        <button
          className={styles.gateBtn}
          onClick={onIndex}
          disabled={!adoId || indexing}
        >
          {indexing ? "Indexando..." : "Fetch & index"}
        </button>
        <button
          className={styles.gateBtn}
          onClick={() => onAnalyze(false)}
          disabled={unanalyzedCount === 0 || analyzing}
          title={
            unanalyzedCount === 0
              ? "No hay comentarios sin analizar"
              : `Analizar ${unanalyzedCount} comentario(s)`
          }
        >
          {analyzing ? "Analizando..." : `Analyze sentiment (${unanalyzedCount})`}
        </button>
        {sentimentGateFailed && (
          <button
            className={`${styles.gateBtn} ${styles.danger}`}
            onClick={() => onAnalyze(true)}
            disabled={analyzing}
            title="Bypassa el gate del eval (debug)"
          >
            Force unsafe
          </button>
        )}
        <span className={styles.commentsHint}>
          pii_masked · advisory_only
        </span>
      </div>

      {lastIndex && (
        <div className={styles.gateMetrics} style={{ marginBottom: 8 }}>
          <span>
            Último index: {lastIndex.inserted} nuevos · {lastIndex.skipped_duplicates} ya
            indexados · {lastIndex.total_fetched} traídos de ADO
          </span>
        </div>
      )}
      {lastAnalyze && (
        <div className={styles.gateMetrics} style={{ marginBottom: 8 }}>
          <span>
            Último analyze: {lastAnalyze.analyzed} OK · {lastAnalyze.failures} fallos ·
            costo {formatCostUsd(lastAnalyze.cost_usd)}
          </span>
          {!lastAnalyze.gate_passed && (
            <span style={{ color: "#fca5a5" }}>
              ⚠ eval gate no pasó — el resultado puede no haberse persistido
            </span>
          )}
        </div>
      )}

      {loading ? (
        <div className={styles.empty}>Cargando comentarios...</div>
      ) : comments.length === 0 ? (
        <div className={styles.empty}>
          {adoId
            ? `No hay comentarios indexados para ADO ${adoId}. Hacé click en "Fetch & index" para traerlos desde ADO.`
            : "Ingresá un ADO ID arriba para indexar los comentarios del work item."}
        </div>
      ) : (
        <div className={styles.commentsList}>
          {comments.map((c) => {
            const sCls = sentimentClass(c.sentiment_label);
            return (
              <div
                key={c.id}
                className={`${styles.commentItem} ${sCls} ${!c.ai_analyzed ? styles.unanalyzed : ""}`}
              >
                <div className={styles.commentHeader}>
                  <span className={`${styles.sentimentBadge} ${sCls}`}>
                    {c.ai_analyzed
                      ? `${c.sentiment_label ?? "neutral"} ${c.sentiment_score != null ? `(${formatPercent(c.sentiment_score * 100)})` : ""}`
                      : "unanalyzed"}
                  </span>
                  <span>{c.author ?? "?"}</span>
                  <span>{c.comment_date ?? "—"}</span>
                </div>
                <div className={styles.commentText}>{stripHashMarker(c.text_plain)}</div>
                <div className={styles.commentMeta}>
                  <span>id interno: {c.id}</span>
                  <span>indexed: {formatDateTime(c.indexed_at)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const MODEL_LS_KEY = "pm.selectedModel";

function readPersistedModel(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(MODEL_LS_KEY);
    return v && v.length > 0 ? v : null;
  } catch {
    return null;
  }
}

function persistModel(model: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(MODEL_LS_KEY, model);
  } catch {
    /* ignore */
  }
}

export default function PMCommandCenter() {
  const qc = useQueryClient();
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("ALL");
  const [showAcked, setShowAcked] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [aiWindow, setAiWindow] = useState<number>(24);
  const [selectedModel, setSelectedModel] = useState<string | null>(readPersistedModel());

  const modelsQuery = useQuery({
    queryKey: ["pm.ai.models"],
    queryFn: () => PmApi.aiModels(),
    staleTime: 5 * 60_000,
  });

  // Cuando llega la lista de modelos: si no hay selección o la persistida ya
  // no existe en la lista, caer al default que reporta el backend.
  React.useEffect(() => {
    const report = modelsQuery.data;
    if (!report) return;
    const availableIds = new Set(report.models.map((m) => m.id));
    if (!selectedModel || !availableIds.has(selectedModel)) {
      setSelectedModel(report.default_model);
      persistModel(report.default_model);
    }
  }, [modelsQuery.data, selectedModel]);

  const activeModel = selectedModel ?? modelsQuery.data?.default_model ?? "mock-1.0";

  const handleModelChange = (model: string) => {
    setSelectedModel(model);
    persistModel(model);
  };

  const pmProject = useWorkbench((s) => s.activeProject?.name ?? null);

  const sprintQuery = useQuery({
    queryKey: ["pm.sprint.current", pmProject],
    queryFn: async () => {
      try {
        return await PmApi.sprintCurrent();
      } catch (e: unknown) {
        // 404 NO_SNAPSHOT no es error real — devolvemos null
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("404")) return null;
        throw e;
      }
    },
    staleTime: 30_000,
  });

  const risksQuery = useQuery({
    queryKey: ["pm.risks", pmProject, severityFilter, showAcked],
    queryFn: async () => {
      const params: Parameters<typeof PmApi.listRisks>[0] = {};
      if (severityFilter !== "ALL") params.severity = severityFilter;
      if (!showAcked) params.acknowledged = false;
      const res = await PmApi.listRisks(params);
      return res.risks;
    },
    staleTime: 30_000,
  });

  const syncMutation = useMutation({
    mutationFn: () => PmApi.syncAdo({}),
    onSuccess: () => {
      setSyncError(null);
      qc.invalidateQueries({ queryKey: ["pm.sprint.current"] });
      qc.invalidateQueries({ queryKey: ["pm.risks"] });
    },
    onError: (e: unknown) => {
      setSyncError(e instanceof Error ? e.message : String(e));
    },
  });

  const ackMutation = useMutation({
    mutationFn: (riskId: string) => PmApi.acknowledgeRisk(riskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm.risks"] });
    },
  });

  const aiUsageQuery = useQuery({
    queryKey: ["pm.ai.usage", aiWindow],
    queryFn: () => PmApi.aiUsage({ since_hours: aiWindow }),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const [sentimentReport, setSentimentReport] = useState<PmEvalReport | null>(null);
  const [recReport, setRecReport] = useState<PmEvalReport | null>(null);
  const [lastRecRun, setLastRecRun] = useState<PmRecommendationRunResult | null>(null);

  const evalsMutation = useMutation({
    mutationFn: (component: EvalComponent) =>
      PmApi.runEvals({ component, model: activeModel }),
    onSuccess: (report) => {
      if (report.component === "comment_sentiment") setSentimentReport(report);
      else if (report.component === "recommendation_engine") setRecReport(report);
      qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
    },
  });

  const generateRecsMutation = useMutation({
    mutationFn: (forceUnsafe: boolean) =>
      PmApi.generateRecommendations({ force_unsafe: forceUnsafe, model: activeModel }),
    onSuccess: (result) => {
      setLastRecRun(result);
      qc.invalidateQueries({ queryKey: ["pm.recommendations"] });
      qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
    },
    onError: (e: unknown) => {
      // El backend retorna 412 cuando el gate no pasa — capturamos el mensaje
      console.warn("generate recommendations failed:", e);
    },
  });

  const recsQuery = useQuery({
    queryKey: ["pm.recommendations"],
    queryFn: () => PmApi.listRecommendations(),
    staleTime: 30_000,
  });

  const ackRecMutation = useMutation({
    mutationFn: (recId: string) => PmApi.acknowledgeRecommendation(recId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm.recommendations"] });
    },
  });

  // ── comments explorer ──────────────────────────────────────────────────────
  const [commentsAdoId, setCommentsAdoId] = useState<number | null>(null);
  const [lastIndex, setLastIndex] = useState<
    { inserted: number; skipped_duplicates: number; total_fetched: number } | null
  >(null);
  const [lastAnalyze, setLastAnalyze] = useState<
    { analyzed: number; failures: number; gate_passed: boolean; cost_usd: number } | null
  >(null);

  const commentsQuery = useQuery({
    queryKey: ["pm.comments", commentsAdoId],
    queryFn: () => PmApi.listComments(commentsAdoId!, 50),
    enabled: commentsAdoId !== null && commentsAdoId > 0,
    staleTime: 15_000,
  });

  const indexMutation = useMutation({
    mutationFn: (adoId: number) =>
      PmApi.indexComments({ ado_ids: [adoId], top_per_item: 50 }),
    onSuccess: (result) => {
      setLastIndex({
        inserted: result.inserted,
        skipped_duplicates: result.skipped_duplicates,
        total_fetched: result.total_fetched,
      });
      qc.invalidateQueries({ queryKey: ["pm.comments"] });
    },
  });

  const sentimentMutation = useMutation({
    mutationFn: ({ ids, force }: { ids: number[]; force: boolean }) =>
      PmApi.analyzeSentiment({
        comment_ids: ids,
        model: activeModel,
        force_unsafe: force,
      }),
    onSuccess: (result) => {
      setLastAnalyze({
        analyzed: result.analyzed,
        failures: result.failures,
        gate_passed: result.gate_passed,
        cost_usd: result.cost_usd,
      });
      qc.invalidateQueries({ queryKey: ["pm.comments"] });
      qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
    },
    onError: (e: unknown) => {
      console.warn("sentiment analyze failed:", e);
      setLastAnalyze({ analyzed: 0, failures: 0, gate_passed: false, cost_usd: 0 });
    },
  });

  const snapshot = sprintQuery.data?.snapshot ?? null;
  const capturedAt = sprintQuery.data?.snapshot?.captured_at ?? null;
  const risks = risksQuery.data ?? [];

  const summary = useMemo(() => {
    const highCount = risks.filter(r => r.severity === "HIGH" || r.severity === "CRITICAL").length;
    const mediumCount = risks.filter(r => r.severity === "MEDIUM").length;
    return { highCount, mediumCount };
  }, [risks]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>📊 PM Command Center</h1>
        <span className={styles.subtitle}>
          Fase 1 MVP · sin IA · azure_devops únicamente
        </span>
        <span className={styles.advisoryBadge}>advisory_only</span>
        <div className={styles.headerActions}>
          <button
            className={styles.btnPrimary}
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending ? "Sincronizando..." : "↻ Sync ADO"}
          </button>
          <button
            className={styles.btnGhost}
            onClick={() => {
              qc.invalidateQueries({ queryKey: ["pm.sprint.current"] });
              qc.invalidateQueries({ queryKey: ["pm.risks"] });
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className={styles.content}>
        {syncError && (
          <div className={styles.bannerError}>
            <strong>Sync falló:</strong> {syncError}
          </div>
        )}

        {!snapshot && !sprintQuery.isLoading && (
          <div className={styles.bannerInfo}>
            No hay snapshots PM para este proyecto. Hacé click en <strong>Sync ADO</strong> para
            traer el sprint actual y calcular KPIs/riesgos determinísticos.
          </div>
        )}

        {sprintQuery.isLoading && <div className={styles.empty}>Cargando sprint actual...</div>}

        {(snapshot || sprintQuery.isLoading) && (
          <SprintHealthCard snapshot={snapshot} capturedAt={capturedAt} />
        )}

        <WeeklyDigestCard />

        <section className={styles.riskSection}>
          <h3 className={styles.sectionTitle}>
            Riesgos detectados ({summary.highCount} altos · {summary.mediumCount} medios)
          </h3>
          <div className={styles.filterBar}>
            <span className={styles.filterLabel}>Severidad:</span>
            <select
              className={styles.filterSelect}
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as SeverityFilter)}
            >
              <option value="ALL">Todas</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
            <label className={styles.filterLabel}>
              <input
                type="checkbox"
                checked={showAcked}
                onChange={(e) => setShowAcked(e.target.checked)}
                style={{ marginRight: 4 }}
              />
              Mostrar acknowledged
            </label>
            <span className={styles.advisoryBadge}>
              ai_enriched: false · reglas deterministas
            </span>
          </div>
          {risksQuery.isLoading ? (
            <div className={styles.empty}>Cargando riesgos...</div>
          ) : (
            <RiskFeed
              risks={risks}
              onAcknowledge={(id) => ackMutation.mutate(id)}
              ackInFlight={ackMutation.isPending ? ackMutation.variables ?? null : null}
            />
          )}
        </section>

        <AIControlPanel
          sentimentReport={sentimentReport}
          recReport={recReport}
          onRunEvals={(c) => evalsMutation.mutate(c)}
          onGenerateRecs={(force) => generateRecsMutation.mutate(force)}
          runningEvals={
            evalsMutation.isPending ? (evalsMutation.variables ?? null) : null
          }
          generatingRecs={generateRecsMutation.isPending}
          lastRecRun={lastRecRun}
          modelsReport={modelsQuery.data ?? null}
          modelsLoading={modelsQuery.isLoading}
          selectedModel={activeModel}
          onModelChange={handleModelChange}
        />

        <section className={styles.recPanel}>
          <h3 className={styles.sectionTitle}>
            Recomendaciones IA generadas
            {recsQuery.data && ` (${recsQuery.data.count})`}
          </h3>
          {recsQuery.isLoading ? (
            <div className={styles.empty}>Cargando recomendaciones...</div>
          ) : (
            <RecommendationFeed
              recommendations={recsQuery.data?.recommendations ?? []}
              onAcknowledge={(id) => ackRecMutation.mutate(id)}
              ackInFlight={
                ackRecMutation.isPending ? (ackRecMutation.variables ?? null) : null
              }
            />
          )}
        </section>

        <CommentsExplorer
          adoId={commentsAdoId}
          onAdoIdChange={setCommentsAdoId}
          comments={commentsQuery.data?.comments ?? []}
          loading={commentsQuery.isLoading}
          indexing={indexMutation.isPending}
          analyzing={sentimentMutation.isPending}
          lastIndex={lastIndex}
          lastAnalyze={lastAnalyze}
          onIndex={() => {
            if (commentsAdoId !== null && commentsAdoId > 0) {
              indexMutation.mutate(commentsAdoId);
            }
          }}
          onAnalyze={(force) => {
            const unanalyzed = (commentsQuery.data?.comments ?? [])
              .filter((c) => !c.ai_analyzed)
              .map((c) => c.id);
            if (unanalyzed.length > 0) {
              sentimentMutation.mutate({ ids: unanalyzed, force });
            }
          }}
        />

        <AIUsagePanel
          report={aiUsageQuery.data ?? null}
          windowHours={aiWindow}
          onWindowChange={setAiWindow}
          loading={aiUsageQuery.isLoading}
        />
      </div>
    </div>
  );
}

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PmApi,
  type PmRiskItem,
  type PmSprintKpis,
  type PmSprintSnapshotRow,
} from "../api/pm";
import styles from "./PMCommandCenter.module.css";

type SeverityFilter = "ALL" | "HIGH" | "MEDIUM" | "LOW" | "CRITICAL";

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-AR", { hour12: false });
  } catch {
    return iso;
  }
}

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
          {fmtDate(iteration?.start_date ?? snapshot?.start_date ?? null)}
          {" → "}
          {fmtDate(iteration?.end_date ?? snapshot?.end_date ?? null)}
        </span>
        <span className={`${styles.healthPill} ${healthClass(kpis)}`}>
          {healthLabel(kpis)}
        </span>
        {capturedAt && (
          <span className={styles.sprintMeta}>
            Último sync: {fmtDateTime(capturedAt)}
          </span>
        )}
      </div>

      <div className={styles.kpiGrid}>
        <KpiCard
          label="Completion"
          value={kpis ? `${kpis.completion_rate_pct.toFixed(0)}%` : "—"}
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
          sub={kpis ? `${kpis.bug_rate_pct.toFixed(1)}% del sprint` : undefined}
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
                  ✓ acknowledged por {r.acknowledged_by ?? "?"} ({fmtDateTime(r.acknowledged_at)})
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
              <span>Detectado: {fmtDateTime(r.detected_at)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PMCommandCenter() {
  const qc = useQueryClient();
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("ALL");
  const [showAcked, setShowAcked] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const sprintQuery = useQuery({
    queryKey: ["pm.sprint.current"],
    queryFn: async () => {
      try {
        return await PmApi.sprintCurrent();
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("404")) return null;
        throw e;
      }
    },
    staleTime: 30_000,
  });

  const risksQuery = useQuery({
    queryKey: ["pm.risks", severityFilter, showAcked],
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
      </div>
    </div>
  );
}

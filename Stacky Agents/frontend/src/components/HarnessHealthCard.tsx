/**
 * HarnessHealthCard.tsx — H8: Tarjeta de KPIs de valor agregado del arnés.
 *
 * Consume GET /api/metrics/harness-health y muestra los indicadores que
 * demuestran el valor de Stacky vs el CLI pelado: tasa de completados sin
 * intervención, autocorrecciones que salvaron un run, hit-rate de memoria,
 * costo por ticket y desglose por runtime y proyecto.
 *
 * Patrón: useEffect + api.get (igual que HealthBanner.tsx).
 */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./HarnessHealthCard.module.css";

// ── Tipos ────────────────────────────────────────────────────────────────────

interface RuntimeStats {
  runs: number;
  completed_rate: number | null;
  autocorrection_rate: number | null;
  cost_per_ticket: number | null;
  avg_contract_score: number | null;
  autocorrection_saves: number;
  memory_hit_rate: number | null;
  runaway_stops: number;
}

interface IntegrityKpis {
  runs_condenados_evitados?: number | "--";
  exitos_fantasma_atrapados?: number | "--";
  tasa_referencias_ancladas?: number | "--";
  tasa_exito_real_creacion?: number | "--";
}

interface ExecVerificationKpis {
  verificados?: number;
  tasa_verde_a_la_primera?: number | "--";
  tasa_recuperacion_exec_repair?: number | "--";
  entregables_rotos_atrapados?: number;
  verde_falso_atrapado?: number;
  costo_medio_verificacion_ms?: number | "--";
}

interface AcceptanceContractKpis {
  total?: number;
  con_contrato?: number;
  tasa_contrato_derivable?: number | "--";
  cumplido_a_la_primera?: number;
  tasa_cumplido_a_la_primera?: number | "--";
  repair_attempted?: number;
  repair_recovered?: number;
  tasa_recuperacion?: number | "--";
  calidad_del_examen?: number | "--";
  intentos_de_gameo_atrapados?: number;
}

interface HarnessHealthResponse {
  ok: boolean;
  generated_at: string;
  window_days: number;
  total_runs: number;
  completed: number;
  needs_review: number;
  errored: number;
  completed_without_intervention_rate: number | null;
  autocorrection_rate: number | null;
  total_cost_usd: number;
  cost_per_ticket_usd: number | null;
  runs_with_cost_telemetry: number;
  autocorrection_saves: number;
  memory_hit_rate: number | null;
  runaway_stops: number;
  by_runtime: Record<string, RuntimeStats>;
  by_project: Record<string, RuntimeStats>;
  // V0.3 / V0.4 / V0.5
  active_runs?: number;
  failure_kinds?: Record<string, number>;
  estimated_cost_runs?: number;
  // Plan 30 — G2.1
  integrity?: IntegrityKpis;
  // Plan 31 — E2.2
  exec_verification_kpis?: ExecVerificationKpis;
  // Plan 32 — A2.2
  acceptance_contract_kpis?: AcceptanceContractKpis;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function pct(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function usd(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toFixed(4)}`;
}

function fmt(value: number | null | undefined): string {
  if (value == null) return "—";
  return String(value);
}

// Plan 30 — valor de KPI de integridad: "--" → "—", tasa → porcentaje, count → string.
function integrityFmt(value: number | "--" | undefined, isTasa: boolean): string {
  if (value === undefined || value === "--") return "—";
  if (isTasa) return `${(value * 100).toFixed(1)}%`;
  return String(value);
}

// V0.4 — "kind: count, kind: count" ordenado desc por count.
function topFailures(kinds: Record<string, number> | undefined): string {
  if (!kinds || Object.keys(kinds).length === 0) return "—";
  return Object.entries(kinds)
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${k}: ${n}`)
    .join(", ");
}

// ── Sub-componentes ──────────────────────────────────────────────────────────

function KpiRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.kpiRow}>
      <span className={styles.kpiLabel}>{label}</span>
      <span className={styles.kpiValue}>{value}</span>
    </div>
  );
}

function RuntimeTable({ data }: { data: Record<string, RuntimeStats> }) {
  const runtimes = Object.keys(data);
  if (runtimes.length === 0) return <p className={styles.empty}>Sin datos en la ventana.</p>;
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Runtime</th>
          <th>Runs</th>
          <th>% Completado</th>
          <th>Saves autocorrect</th>
          <th>Hit-rate memoria</th>
          <th>Costo/ticket</th>
          <th>Score contrato</th>
          <th>Runaway stops</th>
        </tr>
      </thead>
      <tbody>
        {runtimes.map((rt) => {
          const s = data[rt];
          return (
            <tr key={rt}>
              <td className={styles.rtName}>{rt}</td>
              <td>{s.runs}</td>
              <td>{pct(s.completed_rate)}</td>
              <td>{s.autocorrection_saves}</td>
              <td>{pct(s.memory_hit_rate)}</td>
              <td>{usd(s.cost_per_ticket)}</td>
              <td>{fmt(s.avg_contract_score)}</td>
              <td>{s.runaway_stops}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ProjectTable({ data }: { data: Record<string, RuntimeStats> }) {
  const projects = Object.keys(data);
  if (projects.length === 0) return <p className={styles.empty}>Sin datos en la ventana.</p>;
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Proyecto</th>
          <th>Runs</th>
          <th>% Completado</th>
          <th>Saves autocorrect</th>
          <th>Hit-rate memoria</th>
          <th>Costo/ticket</th>
        </tr>
      </thead>
      <tbody>
        {projects.map((proj) => {
          const s = data[proj];
          return (
            <tr key={proj}>
              <td className={styles.rtName}>{proj}</td>
              <td>{s.runs}</td>
              <td>{pct(s.completed_rate)}</td>
              <td>{s.autocorrection_saves}</td>
              <td>{pct(s.memory_hit_rate)}</td>
              <td>{usd(s.cost_per_ticket)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────

interface Props {
  /** Ventana de días a consultar (default 14). */
  days?: number;
}

export default function HarnessHealthCard({ days = 14 }: Props) {
  const [data, setData] = useState<HarnessHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [section, setSection] = useState<"runtime" | "project">("runtime");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .get<HarnessHealthResponse>(`/api/metrics/harness-health?days=${days}`)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar el reporte de salud del arnés.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [days]);

  if (loading) {
    return <div className={styles.card}><p className={styles.loading}>Cargando KPIs...</p></div>;
  }

  if (error || !data) {
    return (
      <div className={`${styles.card} ${styles.cardError}`}>
        <p className={styles.errorMsg}>{error ?? "Sin datos."}</p>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Valor agregado del arnés</h2>
        <span className={styles.window}>Ultimos {data.window_days} dias</span>
      </div>

      {/* KPIs globales */}
      <div className={styles.kpiGrid}>
        <KpiRow label="Runs totales" value={String(data.total_runs)} />
        <KpiRow
          label="Completados sin intervencion"
          value={pct(data.completed_without_intervention_rate)}
        />
        <KpiRow label="Autocorrecciones que salvaron un run" value={String(data.autocorrection_saves)} />
        <KpiRow label="Hit-rate de memoria colaborativa" value={pct(data.memory_hit_rate)} />
        <KpiRow label="Costo total (USD)" value={usd(data.total_cost_usd)} />
        <KpiRow label="Costo por ticket" value={usd(data.cost_per_ticket_usd)} />
        <KpiRow label="Runs frenados por runaway guard" value={String(data.runaway_stops)} />
        <KpiRow label="Runs con telemetria de costo" value={String(data.runs_with_cost_telemetry)} />
        {/* V0.3 / V0.5 */}
        <KpiRow label="Runs CLI activos ahora" value={String(data.active_runs ?? 0)} />
        <KpiRow label="Runs con costo estimado" value={String(data.estimated_cost_runs ?? 0)} />
        {/* V0.4 — Top fallos por causa (orden desc) */}
        <KpiRow label="Top fallos" value={topFailures(data.failure_kinds)} />
      </div>

      {/* Plan 30 — KPIs de integridad (solo si el flag está activo y el endpoint devuelve datos) */}
      {data.integrity && Object.keys(data.integrity).length > 0 && (
        <div className={styles.kpiGrid}>
          <h3 className={styles.title}>Integridad verificada</h3>
          <KpiRow
            label="Runs condenados evitados"
            value={integrityFmt(data.integrity.runs_condenados_evitados, false)}
          />
          <KpiRow
            label="Exitos fantasma atrapados"
            value={integrityFmt(data.integrity.exitos_fantasma_atrapados, false)}
          />
          <KpiRow
            label="Tasa referencias ancladas"
            value={integrityFmt(data.integrity.tasa_referencias_ancladas, true)}
          />
          <KpiRow
            label="Tasa exito real creacion"
            value={integrityFmt(data.integrity.tasa_exito_real_creacion, true)}
          />
        </div>
      )}

      {/* Plan 31 — E2.1/E2.2: KPIs de verificacion ejecutable (solo si flag ON y datos) */}
      {data.exec_verification_kpis && Object.keys(data.exec_verification_kpis).length > 0 &&
       (data.exec_verification_kpis.verificados ?? 0) > 0 && (
        <div className={styles.kpiGrid}>
          <h3 className={styles.title}>Verificacion ejecutable</h3>
          <KpiRow label="Verificados" value={String(data.exec_verification_kpis.verificados ?? 0)} />
          <KpiRow
            label="Tasa verde a la primera"
            value={integrityFmt(data.exec_verification_kpis.tasa_verde_a_la_primera, true)}
          />
          <KpiRow
            label="Tasa recuperacion exec-repair"
            value={integrityFmt(data.exec_verification_kpis.tasa_recuperacion_exec_repair, true)}
          />
          <KpiRow
            label="Entregables rotos atrapados"
            value={String(data.exec_verification_kpis.entregables_rotos_atrapados ?? 0)}
          />
          <KpiRow
            label="Verde falso atrapado"
            value={String(data.exec_verification_kpis.verde_falso_atrapado ?? 0)}
          />
          <KpiRow
            label="Costo medio verificacion (ms)"
            value={integrityFmt(data.exec_verification_kpis.costo_medio_verificacion_ms, false)}
          />
        </div>
      )}

      {/* Plan 32 — A2.1/A2.2: KPIs del contrato de aceptacion (solo si flag ON y datos) */}
      {data.acceptance_contract_kpis && Object.keys(data.acceptance_contract_kpis).length > 0 &&
       (data.acceptance_contract_kpis.total ?? 0) > 0 && (
        <div className={styles.kpiGrid}>
          <h3 className={styles.title}>Contrato de aceptacion</h3>
          <KpiRow
            label="Tasa contrato derivable"
            value={integrityFmt(data.acceptance_contract_kpis.tasa_contrato_derivable, true)}
          />
          <KpiRow
            label="Tasa cumplido a la primera"
            value={integrityFmt(data.acceptance_contract_kpis.tasa_cumplido_a_la_primera, true)}
          />
          <KpiRow
            label="Tasa recuperacion (repair)"
            value={integrityFmt(data.acceptance_contract_kpis.tasa_recuperacion, true)}
          />
          <KpiRow
            label="Calidad del examen"
            value={integrityFmt(data.acceptance_contract_kpis.calidad_del_examen, true)}
          />
          <KpiRow
            label="Intentos de gameo atrapados"
            value={String(data.acceptance_contract_kpis.intentos_de_gameo_atrapados ?? 0)}
          />
        </div>
      )}

      {/* Selector runtime / proyecto */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${section === "runtime" ? styles.tabActive : ""}`}
          onClick={() => setSection("runtime")}
        >
          Por runtime
        </button>
        <button
          className={`${styles.tab} ${section === "project" ? styles.tabActive : ""}`}
          onClick={() => setSection("project")}
        >
          Por proyecto
        </button>
      </div>

      {section === "runtime" && <RuntimeTable data={data.by_runtime} />}
      {section === "project" && <ProjectTable data={data.by_project} />}

      <p className={styles.generatedAt}>
        Generado: {new Date(data.generated_at).toLocaleString()}
      </p>
    </div>
  );
}

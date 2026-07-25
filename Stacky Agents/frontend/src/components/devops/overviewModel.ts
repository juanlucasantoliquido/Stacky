/** Plan 239 F2 — modelo puro del Resumen DevOps. Sin React, sin fetch, sin DOM. */

export type OverviewTone = "success" | "warning" | "danger" | "info" | "neutral";
export type OverviewStatus = "ok" | "warning" | "danger" | "unknown";

export interface OverviewFilters {
  app_id: string | null;
  project: string | null;
  window_days: number;
}

export interface OverviewOptions {
  apps: { id: string; name: string }[];
  projects: string[];
}

export interface OverviewKpis {
  deploys_7d: number;
  deploys_30d: number;
  change_failure_rate_30d: number | null;
  cfr_sample_30d: number;
  mttr_minutes_30d: number | null;
  last_deploy_at: string | null;
  ci_runs_7d: number;
  ci_failures_7d: number;
  ci_running_now: number;
  connections_ok: number | null;
  connections_total: number | null;
  servers_total: number;
  apps_total: number;
  targets_configured: number;
  targets_locked: number;
}

export interface OverviewSeries {
  days: string[];
  deploys_by_day: number[];
  deploy_failures_by_day: number[];
  ci_runs_by_day: number[];
  ci_failures_by_day: number[];
}

export interface OverviewAlert {
  id: string;
  tone: OverviewTone;
  title: string;
  detail: string;
  section: string;
}

export interface OverviewEvent {
  at: string;
  kind: "deploy" | "ci";
  tone: OverviewTone;
  title: string;
  status: string;
  section: string;
  app_id: string | null;
  project: string | null;
}

export type OverviewBlockKey = "deployments" | "ci" | "connections" | "servers";
export interface OverviewBlock {
  available: boolean;
  reason: null | "flag_off" | "sin_datos" | "error_lectura";
}

/** Espejo EXACTO del contrato F1.1. */
export interface OverviewPayload {
  generated_at: string;
  status: OverviewStatus;
  filters: OverviewFilters;
  options: OverviewOptions;
  kpis: OverviewKpis;
  series: OverviewSeries;
  alerts: OverviewAlert[];
  recent: OverviewEvent[];
  blocks: Record<OverviewBlockKey, OverviewBlock>;
}

export interface KpiRow {
  key: string;
  label: string;
  value: string;
  hint?: string;
  tone?: OverviewTone;
}

const ND = "n/d";

/** null/undefined ⇒ "n/d" SIEMPRE (precedente formatUsd de CostKpiCards, plan 142 F6).
 *  Prohibido devolver "0" para un dato ausente. 0 SÍ es un dato y se muestra. */
export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return ND;
  return String(Math.round(n));
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return ND;
  return `${Math.round(v * 100)}%`;
}

export function fmtMinutes(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return ND;
  const total = Math.round(v);
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export function fmtWhen(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return ND;
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return ND;
  const dias = Math.floor((nowMs - ms) / 86_400_000);
  if (dias <= 0) return "hoy";
  if (dias === 1) return "ayer";
  return `hace ${dias} días`;
}

function cfrTone(v: number | null): OverviewTone | undefined {
  if (v === null || v === undefined) return undefined;
  if (v >= 0.3) return "danger";
  if (v < 0.1) return "success";
  return "warning";
}

/** 8 KPIs en ORDEN FIJO: deploys_7d, change_failure_rate_30d, mttr_minutes_30d,
 *  last_deploy_at, ci_runs_7d, ci_failures_7d, connections, servers_total. */
export function buildKpiRows(p: OverviewPayload, nowMs: number): KpiRow[] {
  const k = p.kpis;
  const conexiones =
    k.connections_total === null || k.connections_total === undefined
      ? ND
      : `${fmtInt(k.connections_ok)} / ${fmtInt(k.connections_total)}`;
  return [
    { key: "deploys_7d", label: "Despliegues (7 d)", value: fmtInt(k.deploys_7d),
      hint: `${fmtInt(k.deploys_30d)} en 30 días` },
    { key: "change_failure_rate_30d", label: "Fallos de despliegue (30 d)",
      value: fmtPct(k.change_failure_rate_30d),
      hint: `Sobre ${fmtInt(k.cfr_sample_30d)} despliegues terminados`,
      tone: cfrTone(k.change_failure_rate_30d) },
    { key: "mttr_minutes_30d", label: "Recuperación (30 d)", value: fmtMinutes(k.mttr_minutes_30d),
      hint: "Tiempo hasta el siguiente despliegue exitoso",
      tone: k.mttr_minutes_30d !== null && k.mttr_minutes_30d >= 240 ? "warning" : undefined },
    { key: "last_deploy_at", label: "Último despliegue", value: fmtWhen(k.last_deploy_at, nowMs) },
    { key: "ci_runs_7d", label: "Corridas de CI (7 d)", value: fmtInt(k.ci_runs_7d),
      hint: `${fmtInt(k.ci_running_now)} en curso` },
    { key: "ci_failures_7d", label: "Fallos de CI (7 d)", value: fmtInt(k.ci_failures_7d),
      tone: k.ci_failures_7d >= 2 ? "warning" : undefined },
    { key: "connections", label: "Conexiones en verde", value: conexiones,
      hint: k.connections_total === null ? "Nunca se corrió el chequeo" : undefined },
    { key: "servers_total", label: "Servidores", value: fmtInt(k.servers_total),
      hint: `${fmtInt(k.targets_configured)} destinos configurados` },
  ];
}

export function statusLabel(s: OverviewStatus): { text: string; tone: OverviewTone } {
  switch (s) {
    case "ok":
      return { text: "Sin novedades", tone: "success" };
    case "warning":
      return { text: "Requiere atención", tone: "warning" };
    case "danger":
      return { text: "Hay algo roto", tone: "danger" };
    default:
      // NUNCA "todo bien": sin datos no se puede afirmar que esté bien (guardarraíl 6).
      return { text: "Sin datos suficientes", tone: "neutral" };
  }
}

const BLOCK_LABELS: Record<OverviewBlockKey, string> = {
  deployments: "Despliegues",
  ci: "CI",
  connections: "Conexiones",
  servers: "Servidores",
};

const REASON_LABELS: Record<string, string> = {
  flag_off: "bitácora apagada",
  sin_datos: "sin datos todavía",
  error_lectura: "no se pudo leer",
};

/** Texto de los bloques apagados: "CI: bitácora apagada · Conexiones: sin chequear".
 *  Devuelve "" si los 4 bloques están disponibles con datos. */
export function blocksNote(p: OverviewPayload): string {
  const partes: string[] = [];
  (Object.keys(BLOCK_LABELS) as OverviewBlockKey[]).forEach((key) => {
    const b = p.blocks?.[key];
    if (!b) return;
    if (b.available && b.reason === null) return;
    const motivo = REASON_LABELS[b.reason ?? ""] ?? "sin datos";
    partes.push(`${BLOCK_LABELS[key]}: ${motivo}`);
  });
  return partes.join(" · ");
}

/** Polyline SVG normalizada a un viewBox 100x30. Serie vacía o toda en cero ⇒ "" (no dibuja). */
export function sparkPoints(series: number[], width = 100, height = 30): string {
  const datos = series ?? [];
  if (datos.length === 0) return "";
  const max = Math.max(...datos);
  if (max <= 0) return "";
  const paso = datos.length === 1 ? 0 : width / (datos.length - 1);
  return datos
    .map((v, i) => {
      const x = datos.length === 1 ? width / 2 : i * paso;
      const y = height - (v / max) * height;
      return `${Math.round(x * 100) / 100},${Math.round(y * 100) / 100}`;
    })
    .join(" ");
}

/** Resumen textual de la serie para lectores de pantalla (la sparkline va aria-hidden). */
export function sparkAltText(label: string, series: number[], days: string[]): string {
  const datos = series ?? [];
  const total = datos.reduce((a, b) => a + b, 0);
  const max = datos.length ? Math.max(...datos) : 0;
  const ventana = days?.length ?? datos.length;
  return `${label}: ${total} en ${ventana} días, máximo ${max} en un día.`;
}

const TONE_WORD: Record<string, string> = {
  danger: "Crítico",
  warning: "Atención",
  info: "Info",
  success: "OK",
  neutral: "Info",
};

/** [ADICIÓN ARQUITECTO] (v2) — El resumen del cockpit como texto llano, para pegarlo en
 *  un ticket, un chat o el standup. Función PURA: recibe el payload, devuelve un string.
 *
 *  Reglas duras: (1) reusa buildKpiRows/statusLabel/blocksNote — prohibido reformatear
 *  a mano, o el texto miente cuando la pantalla dice otra cosa; (2) jamás imprime "0"
 *  por un dato ausente; (3) no incluye logs, rutas ni nombres de host. */
export function buildOverviewClipboardText(p: OverviewPayload, nowMs: number): string {
  const st = statusLabel(p.status);
  const alcanceApp = p.filters?.app_id
    ? (p.options?.apps?.find((a) => a.id === p.filters.app_id)?.name ?? p.filters.app_id)
    : "todas las aplicaciones";
  const alcanceProy = p.filters?.project ?? "todos los proyectos de CI";
  const lineas: string[] = [
    `DevOps — ${st.text} · ${p.generated_at}`,
    `Alcance: ${alcanceApp} · ${alcanceProy} · ${p.filters?.window_days ?? ""} días`,
    "KPIs:",
  ];
  buildKpiRows(p, nowMs).forEach((k) => lineas.push(`  ${k.label}: ${k.value}`));

  const alertas = p.alerts ?? [];
  lineas.push(`Avisos: ${alertas.length}`);
  if (alertas.length === 0) {
    lineas.push("  (ninguno)");
  } else {
    alertas.forEach((a) =>
      lineas.push(`  - [${TONE_WORD[a.tone] ?? "Info"}] ${a.title} — ${a.detail}`),
    );
  }

  const note = blocksNote(p);
  lineas.push(`Fuentes sin datos: ${note || "ninguna"}`);
  return lineas.join("\n");
}

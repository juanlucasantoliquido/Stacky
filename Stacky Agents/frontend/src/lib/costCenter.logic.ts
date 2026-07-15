/**
 * Plan 142 F5 — Lógica PURA de presentación del Centro de Costos (sin React).
 * Formatters, sort/filter/CSV de la tabla, y math de charts SVG propios (sin
 * librería de gráficos: R5). Testeada con vitest porque RTL/jsdom no están
 * instalados (gap estructural — ver R6): el gate de los .tsx (F6) es tsc.
 */
import type { CostKind, TopRun } from "./costCenterTypes";

export function formatUsd(n: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "n/d";
  return `$${n.toFixed(2)}`;
}

export function formatTokens(n: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "n/d";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function formatPct(n: number): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "0%";
  return `${Math.round(n * 100)}%`;
}

export function sortRows<T>(rows: T[], key: keyof T, dir: "asc" | "desc"): T[] {
  const mul = dir === "asc" ? 1 : -1;
  // .slice() antes de .sort(): nunca muta el array de entrada. Array.prototype.sort
  // es estable (garantizado desde ES2019) — orden relativo de iguales se preserva.
  return rows.slice().sort((a, b) => {
    const av = a[key] as unknown as string | number | null | undefined;
    const bv = b[key] as unknown as string | number | null | undefined;
    if (av == null && bv == null) return 0;
    if (av == null) return 1;   // "n/d" siempre al final, sin importar la dirección
    if (bv == null) return -1;
    if (av < bv) return -1 * mul;
    if (av > bv) return 1 * mul;
    return 0;
  });
}

export interface TableFilterState {
  runtime?: string;
  model?: string;
  agent_type?: string;
  ticket_id?: number;
  cost_kind?: CostKind;
}

export function filterRows(rows: TopRun[], f: TableFilterState): TopRun[] {
  return rows.filter((r) => {
    if (f.runtime && r.runtime !== f.runtime) return false;
    if (f.model && r.model !== f.model) return false;
    if (f.agent_type && r.agent_type !== f.agent_type) return false;
    if (f.ticket_id != null && r.ticket_id !== f.ticket_id) return false;
    if (f.cost_kind && r.cost_kind !== f.cost_kind) return false;
    return true;
  });
}

const CSV_HEADER = [
  "execution_id", "ticket_id", "agent_type", "runtime", "model", "cost_usd", "cost_kind", "started_at",
] as const;

function csvEscape(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  if (/["\n,]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCsv(rows: TopRun[]): string {
  const lines = [CSV_HEADER.join(",")];
  for (const r of rows) {
    lines.push(
      [r.execution_id, r.ticket_id, r.agent_type, r.runtime, r.model, r.cost_usd, r.cost_kind, r.started_at]
        .map(csvEscape)
        .join(","),
    );
  }
  return lines.join("\n");
}

const COST_KIND_LABELS: Record<CostKind, string> = {
  reported: "Reportado",
  estimated: "Estimado",
  nominal: "Nominal (suscripción)",
  unknown: "n/d",
};

export function costKindLabel(k: CostKind): string {
  return COST_KIND_LABELS[k] ?? "n/d";
}

// Reusa los tokens REALES del design system (Plan 138/141 — StatusChip.module.css):
// --status-success-text / --status-warning-text / --status-info-text / --status-neutral-text.
// PROHIBIDO hex (gate anti-drift Plan 141): siempre var(...), nunca un literal "#RRGGBB".
const COST_KIND_TOKEN_VAR: Record<CostKind, string> = {
  reported: "var(--status-success-text)",
  estimated: "var(--status-warning-text)",
  nominal: "var(--status-info-text)",
  unknown: "var(--status-neutral-text)",
};

export function costKindTokenVar(k: CostKind): string {
  return COST_KIND_TOKEN_VAR[k] ?? COST_KIND_TOKEN_VAR.unknown;
}

// ── Math de SVG (charts sin librería — R5) ───────────────────────────────────

export interface Point {
  x: number;
  y: number;
}

export function linePath(points: Point[]): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
}

export function areaPath(points: Point[], baselineY: number): string {
  if (points.length === 0) return "";
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath(points)} L ${last.x} ${baselineY} L ${first.x} ${baselineY} Z`;
}

export function scaleLinear(domain: [number, number], range: [number, number]): (v: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  return (v: number) => {
    if (span === 0) return r0;
    const t = (v - d0) / span;
    return r0 + t * (r1 - r0);
  };
}

export function niceTicks(min: number, max: number, count: number): number[] {
  const n = Math.max(2, Math.floor(count));
  if (min === max) return Array.from({ length: n }, () => min);
  const step = (max - min) / (n - 1);
  return Array.from({ length: n }, (_, i) => Math.round((min + i * step) * 1e6) / 1e6);
}

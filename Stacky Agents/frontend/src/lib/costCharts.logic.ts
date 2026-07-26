// Plan 199 F5/F6 — Matemática de los tres gráficos nuevos del Centro de Costos.
//
// Todo el cálculo vive acá y se testea sin DOM. Los componentes solo dibujan
// SVG con estos números: cero dependencias nuevas (regla del 142).

export interface StackedPoint {
  bucket: string;
  groups: Record<string, number>;
  billable_usd: number;
}

export interface HeatmapCell {
  weekday: number;
  hour: number;
  billable_usd: number;
  runs: number;
}

export interface DistributionBin {
  lo: number;
  hi: number;
  count: number;
}

export const WEEKDAY_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

// ── Serie apilada ───────────────────────────────────────────────────────────

/** Alto de cada segmento en px, apilados de abajo hacia arriba. */
export function stackSegments(
  point: StackedPoint,
  groups: string[],
  maxTotal: number,
  chartHeight: number
): { group: string; value: number; height: number; y: number }[] {
  if (maxTotal <= 0 || chartHeight <= 0) {
    return groups.map((g) => ({ group: g, value: point.groups?.[g] ?? 0, height: 0, y: chartHeight }));
  }
  let acumulado = 0;
  return groups.map((g) => {
    const value = point.groups?.[g] ?? 0;
    const height = (value / maxTotal) * chartHeight;
    acumulado += height;
    return { group: g, value, height, y: chartHeight - acumulado };
  });
}

export function maxTotalOf(series: StackedPoint[] | null | undefined): number {
  return (series ?? []).reduce((m, p) => Math.max(m, p.billable_usd ?? 0), 0);
}

/** Color estable por grupo: el mismo runtime tiene el mismo color entre
 *  corridas, o comparar dos gráficos sería imposible. */
export function groupColorIndex(group: string, groups: string[]): number {
  const i = groups.indexOf(group);
  return i < 0 ? 0 : i;
}

// ── Heatmap ─────────────────────────────────────────────────────────────────

/** Matriz 7×24 densa: las celdas sin datos existen con cero, para que la grilla
 *  se dibuje completa y un hueco no se lea como "no hay datos todavía". */
export function heatmapGrid(cells: HeatmapCell[] | null | undefined): HeatmapCell[][] {
  const grid: HeatmapCell[][] = Array.from({ length: 7 }, (_, weekday) =>
    Array.from({ length: 24 }, (_, hour) => ({ weekday, hour, billable_usd: 0, runs: 0 }))
  );
  for (const c of cells ?? []) {
    if (c.weekday >= 0 && c.weekday < 7 && c.hour >= 0 && c.hour < 24) {
      grid[c.weekday][c.hour] = c;
    }
  }
  return grid;
}

/** Intensidad 0..1 relativa al máximo. Sin gasto, 0 — no 1 por dividir por cero. */
export function heatIntensity(value: number, max: number): number {
  if (!max || max <= 0) return 0;
  return Math.max(0, Math.min(1, value / max));
}

export function heatmapTooltip(cell: HeatmapCell, formatUsd: (n: number) => string): string {
  const dia = WEEKDAY_LABELS[cell.weekday] ?? "?";
  const hora = String(cell.hour).padStart(2, "0");
  return `${dia} ${hora}:00 · ${formatUsd(cell.billable_usd)} · ${cell.runs} corrida(s)`;
}

// ── Distribución ────────────────────────────────────────────────────────────

export function maxBinCount(bins: DistributionBin[] | null | undefined): number {
  return (bins ?? []).reduce((m, b) => Math.max(m, b.count ?? 0), 0);
}

export function binHeight(count: number, maxCount: number, chartHeight: number): number {
  if (!maxCount || maxCount <= 0) return 0;
  return (count / maxCount) * chartHeight;
}

export function binLabel(bin: DistributionBin, formatUsd: (n: number) => string): string {
  return `${formatUsd(bin.lo)} – ${formatUsd(bin.hi)}`;
}

/**
 * El titular de la distribución. Una cola larga (pocas corridas carísimas) es
 * lo que un promedio esconde, y es lo accionable: ahí está el gasto.
 */
export function distributionHeadline(
  bins: DistributionBin[] | null | undefined,
  total: number
): string {
  const lista = bins ?? [];
  if (!total || !lista.length) return "Sin corridas con costo conocido.";
  const ultimoConDatos = [...lista].reverse().find((b) => b.count > 0);
  const enElUltimoTercio = lista
    .slice(Math.ceil(lista.length * (2 / 3)))
    .reduce((s, b) => s + b.count, 0);
  if (ultimoConDatos && enElUltimoTercio > 0 && enElUltimoTercio / total <= 0.1) {
    return `${enElUltimoTercio} de ${total} corridas concentran el costo más alto.`;
  }
  return `${total} corridas con costo conocido.`;
}

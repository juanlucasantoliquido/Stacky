// Plan 178 — Lógica pura del radar de ambientes (testeable con vitest, sin RTL/jsdom).
import type { CompareRun } from "./dbcompareTypes";
import type { RadarCell, RadarEnvironment } from "./radarTypes";

/** Clave ordenada de un par (agrupa tendencia en cualquier dirección).
 * Se redefine local porque runHistory.ts no la exporta (no se toca ese archivo). */
export function pairKey(a: string, b: string): string {
  return [a, b].sort().join("::");
}

/** Matriz N×N indexada [fila=origen][columna=destino]; null = sin datos (gris),
 * diagonal = null. */
export function buildMatrix(
  environments: { alias: string }[],
  cells: RadarCell[],
): (RadarCell | null)[][] {
  const byPair = new Map<string, RadarCell>();
  for (const c of cells) {
    byPair.set(`${c.source_alias}__${c.target_alias}`, c);
  }
  return environments.map((row) =>
    environments.map((col) => {
      if (row.alias === col.alias) return null;
      return byPair.get(`${row.alias}__${col.alias}`) ?? null;
    }),
  );
}

export function cellStateClass(cell: RadarCell | null): "green" | "amber" | "red" | "gray" {
  if (cell === null) return "gray";
  const sev = cell.by_severity || { info: 0, warn: 0, danger: 0 };
  if ((sev.danger || 0) > 0) return "red";
  if ((sev.warn || 0) > 0 || (sev.info || 0) > 0) return "amber";
  return "green";
}

export interface TrendPoint {
  t: string;
  danger: number;
  warn: number;
  info: number;
}

/** Serie temporal del par (cualquier dirección), runs `done` ordenados ascendente. */
export function trendSeries(
  runs: CompareRun[],
  sourceAlias: string,
  targetAlias: string,
): TrendPoint[] {
  const key = pairKey(sourceAlias, targetAlias);
  return runs
    .filter(
      (r) =>
        r.status === "done" &&
        !!r.summary &&
        pairKey(r.source_alias, r.target_alias) === key,
    )
    .sort((a, b) => (a.finished_at || "").localeCompare(b.finished_at || ""))
    .map((r) => {
      const sev = r.summary!.by_severity;
      return {
        t: r.finished_at || "",
        danger: sev.danger || 0,
        warn: sev.warn || 0,
        info: sev.info || 0,
      };
    });
}

/** Path SVG lineal de la serie danger+warn normalizada. "" si no hay puntos. */
export function sparklinePath(
  points: { danger: number; warn: number }[],
  width: number,
  height: number,
): string {
  if (points.length === 0) return "";
  const values = points.map((p) => Math.max(0, (p.danger || 0) + (p.warn || 0)));
  const max = Math.max(...values, 1);
  const n = points.length;
  const coords = values.map((v, i) => {
    const x = n === 1 ? 0 : Math.round((i / (n - 1)) * width);
    const y = Math.round(height - (v / max) * height);
    return [x, y] as const;
  });
  if (n === 1) {
    const y = coords[0][1];
    return `M0,${y} L${width},${y}`;
  }
  return "M" + coords.map(([x, y]) => `${x},${y}`).join(" L");
}

/** Tiempo relativo determinista (recibe el reloj como argumento). "" si no parsea. */
export function relativeFromIso(iso: string, nowMs: number): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  const delta = nowMs - ms;
  if (delta < 60_000) return "hace <1 min";
  if (delta < 3_600_000) return `hace ${Math.floor(delta / 60_000)} min`;
  if (delta < 86_400_000) return `hace ${Math.floor(delta / 3_600_000)} h`;
  return `hace ${Math.floor(delta / 86_400_000)} d`;
}

export function formatCellTitle(cell: RadarCell, nowMs: number): string {
  const sev = cell.by_severity || { info: 0, warn: 0, danger: 0 };
  const parity = cell.parity_score == null ? "?" : cell.parity_score;
  const when = relativeFromIso(cell.finished_at || "", nowMs);
  const rel = when ? ` · ${when}` : "";
  return `${cell.source_alias} → ${cell.target_alias} · paridad ${parity} · ${sev.danger || 0} danger / ${sev.warn || 0} warn / ${sev.info || 0} info${rel}`;
}

/** Ambientes útiles para la matriz (>= 2 => radar visible). */
export function radarIsMeaningful(
  environments: RadarEnvironment[],
  cells: RadarCell[],
  watches: unknown[],
): boolean {
  return environments.length >= 2 && (cells.length > 0 || watches.length > 0);
}

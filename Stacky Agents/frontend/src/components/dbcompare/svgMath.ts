// Plan 124 — Comparador de BD: helpers puros de SVG para el gauge de paridad (doc §F3).
import type { SchemaDiff, Severity, DiffAction } from "./dbcompareTypes";

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

/** Convierte un ángulo (0deg = arriba, sentido horario) a coordenadas cartesianas. */
export function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180.0;
  return {
    x: round2(cx + r * Math.cos(angleRad)),
    y: round2(cy + r * Math.sin(angleRad)),
  };
}

/** Path SVG "M … A …" horario para un arco. Clampea el barrido a <= 359.99 grados. */
export function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  let sweep = endDeg - startDeg;
  if (sweep > 359.99) sweep = 359.99;
  const clampedEndDeg = startDeg + sweep;
  const start = polarToCartesian(cx, cy, r, startDeg);
  const end = polarToCartesian(cx, cy, r, clampedEndDeg);
  const largeArcFlag = sweep > 180 ? 1 : 0;
  const sweepFlag = 1; // horario
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} ${sweepFlag} ${end.x} ${end.y}`;
}

/** Barrido del gauge de paridad: 270 grados totales, de 135deg a 405deg. */
export function gaugeSweep(score: number): { startDeg: 135; endDeg: number } {
  const clamped = clamp(score, 0, 100);
  return { startDeg: 135, endDeg: 135 + (270 * clamped) / 100 };
}

const SEVERITY_ORDER: Severity[] = ["danger", "warn", "info"];
const ACTION_ORDER: DiffAction[] = ["added", "removed", "changed"];

export function severityCounters(diff: SchemaDiff): { severity: Severity; count: number }[] {
  return SEVERITY_ORDER.map((severity) => ({ severity, count: diff.summary.by_severity[severity] }));
}

export function actionCounters(diff: SchemaDiff): { action: DiffAction; count: number }[] {
  return ACTION_ORDER.map((action) => ({ action, count: diff.summary.by_action[action] }));
}

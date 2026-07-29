/**
 * graphMinimap.ts — Plan 268 F7. Matemática pura del minimapa. Sin canvas.
 */
import type { Viewport } from "./graphViewport";

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/**
 * Transformación mundo → minimapa. El origen del mundo va HORNEADO en los offsets,
 * así que el mapeo es exactamente `mx = x * scale + offsetX` y su inversa
 * `x = (mx - offsetX) / scale`.
 *
 * ⚠️ Desvío del plan (medido, no opinado): el plan declara esta interfaz con solo
 * `{ scale, offsetX, offsetY }`, pero `viewportRectInMinimap` promete devolver un
 * rectángulo CLAMPEADO al minimapa y `viewportFromMinimapClick` necesita invertir el
 * mapeo — con solo escala y offset no hay contra qué clampear. Se agregan `width` y
 * `height` (superset, nadie más consume el tipo).
 */
export interface MinimapTransform {
  scale: number;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Un minimapa nunca AMPLÍA: es un mapa chico, no una lupa. */
export const MINIMAP_MAX_SCALE = 1;

/** Bounding box de los puntos (con radio). Lista vacía → {0,0,0,0}. */
export function boundsOf(points: { x: number; y: number; r?: number }[]): Bounds {
  if (!points.length) return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    const r = p.r ?? 0;
    if (p.x - r < minX) minX = p.x - r;
    if (p.y - r < minY) minY = p.y - r;
    if (p.x + r > maxX) maxX = p.x + r;
    if (p.y + r > maxY) maxY = p.y + r;
  }
  return { minX, minY, maxX, maxY };
}

/** Transformación mundo → minimapa (mmW × mmH px) preservando el aspect ratio y centrando. */
export function minimapTransform(
  b: Bounds,
  mmW: number,
  mmH: number,
  padding: number = 4
): MinimapTransform {
  const spanX = Math.max(1e-6, b.maxX - b.minX);
  const spanY = Math.max(1e-6, b.maxY - b.minY);
  const availW = Math.max(1, mmW - 2 * padding);
  const availH = Math.max(1, mmH - 2 * padding);
  const scale = Math.min(availW / spanX, availH / spanY, MINIMAP_MAX_SCALE);
  const offsetX = padding + (availW - spanX * scale) / 2 - b.minX * scale;
  const offsetY = padding + (availH - spanY * scale) / 2 - b.minY * scale;
  return { scale, offsetX, offsetY, width: mmW, height: mmH };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Rectángulo (en px del minimapa) que representa lo que se ve hoy en el canvas.
 *  CLAMPEADO al rectángulo del minimapa: nunca sale de sus bordes ni da w/h negativos. */
export function viewportRectInMinimap(
  vp: Viewport,
  canvasW: number,
  canvasH: number,
  t: MinimapTransform
): Rect {
  // esquinas del mundo visibles hoy (inversa de toScreen)
  const wx0 = -vp.tx / vp.scale;
  const wy0 = -vp.ty / vp.scale;
  const wx1 = (canvasW - vp.tx) / vp.scale;
  const wy1 = (canvasH - vp.ty) / vp.scale;
  const x0 = clamp(wx0 * t.scale + t.offsetX, 0, t.width);
  const y0 = clamp(wy0 * t.scale + t.offsetY, 0, t.height);
  const x1 = clamp(wx1 * t.scale + t.offsetX, 0, t.width);
  const y1 = clamp(wy1 * t.scale + t.offsetY, 0, t.height);
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
}

/** Click en (mx,my) del minimapa → Viewport centrado en ese punto del mundo, misma escala. */
export function viewportFromMinimapClick(
  vp: Viewport,
  mx: number,
  my: number,
  t: MinimapTransform,
  canvasW: number,
  canvasH: number
): Viewport {
  const wx = (mx - t.offsetX) / t.scale;
  const wy = (my - t.offsetY) / t.scale;
  return {
    scale: vp.scale,
    tx: canvasW / 2 - wx * vp.scale,
    ty: canvasH / 2 - wy * vp.scale,
  };
}

/**
 * (C13) Predicado PURO del nivel de detalle: ¿se dibuja esta arista a esta escala?
 * Sacado de draw() a propósito: dentro de draw() sería intesteable (no hay jsdom ni
 * canvas en este repo), y una regla de dibujo sin test es una regla que nadie sabe
 * si funciona.
 *
 * Regla: a escala < LOD_SCALE_THRESHOLD (0.6) se ocultan las aristas cuyos DOS
 * extremos son nodos poco conectados. "Poco conectado" = radio < LOD_MIN_RADIUS (6).
 * Con nodeRadius(d) = 4 + min(11, d*1.15) (forceLayout), r < 6 equivale EXACTAMENTE a
 * in_degree <= 1 (d=1 → r=5.15; d=2 → r=6.3). O sea: al alejarse se ven los troncos y
 * desaparecen las hojas. A escala >= 0.6 se dibuja todo.
 */
export const LOD_SCALE_THRESHOLD = 0.6;
export const LOD_MIN_RADIUS = 6;

export function shouldDrawEdge(rA: number, rB: number, scale: number): boolean {
  if (scale >= LOD_SCALE_THRESHOLD) return true;
  return !(rA < LOD_MIN_RADIUS && rB < LOD_MIN_RADIUS);
}

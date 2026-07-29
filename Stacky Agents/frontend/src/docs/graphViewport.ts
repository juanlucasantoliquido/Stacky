/**
 * graphViewport.ts — mejora visual del graph view (plan 111).
 *
 * Matemática PURA (sin canvas, sin React, sin DOM) para:
 *   - zoom/pan del grafo (transformación mundo↔pantalla con clamps), y
 *   - selección de labels sin solapamiento (greedy por prioridad).
 * Testeable con vitest sin jsdom.
 */

// ── Viewport (zoom/pan) ──────────────────────────────────────────────────────

export interface Viewport {
  /** factor de escala mundo→pantalla */
  scale: number;
  /** traslación en px de pantalla */
  tx: number;
  ty: number;
}

export const MIN_SCALE = 0.3;
export const MAX_SCALE = 5;

export const IDENTITY: Viewport = { scale: 1, tx: 0, ty: 0 };

function clampScale(s: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
}

/** pantalla → mundo */
export function toWorld(vp: Viewport, sx: number, sy: number): { x: number; y: number } {
  return { x: (sx - vp.tx) / vp.scale, y: (sy - vp.ty) / vp.scale };
}

/** mundo → pantalla */
export function toScreen(vp: Viewport, wx: number, wy: number): { x: number; y: number } {
  return { x: wx * vp.scale + vp.tx, y: wy * vp.scale + vp.ty };
}

/**
 * Zoom multiplicativo manteniendo fijo el punto de pantalla (cx, cy)
 * (el punto del mundo bajo el cursor no se mueve). Escala clampeada.
 */
export function zoomAt(vp: Viewport, factor: number, cx: number, cy: number): Viewport {
  const scale = clampScale(vp.scale * factor);
  if (scale === vp.scale) return vp;
  const k = scale / vp.scale;
  return {
    scale,
    tx: cx - (cx - vp.tx) * k,
    ty: cy - (cy - vp.ty) * k,
  };
}

/** Pan en px de pantalla. */
export function panBy(vp: Viewport, dx: number, dy: number): Viewport {
  return { scale: vp.scale, tx: vp.tx + dx, ty: vp.ty + dy };
}

// ── Plan 268 F0.4 — encuadre y zoom al centro ────────────────────────────────

/** Paso multiplicativo de un click en los botones + / − del zoom. */
export const ZOOM_STEP = 1.25;

/** Tope de escala al encuadrar: nunca ampliar más allá de esto aunque quepa. */
export const MAX_FIT_SCALE = 1.5;

export interface FitPoint {
  x: number;
  y: number;
  r?: number;
}

/**
 * Encuadra `points` dentro de un canvas de width×height dejando `padding` px de margen.
 * - [] → IDENTITY (no hay nada que encuadrar).
 * - 1 punto (o todos coincidentes) → escala min(1.5, MAX_SCALE) y centrado en ese punto.
 * - Escala clampeada a [MIN_SCALE, MAX_SCALE] y además a MAX_FIT_SCALE.
 * El bounding box incluye el radio r de cada punto (default 0).
 */
export function fitViewport(
  points: FitPoint[],
  width: number,
  height: number,
  padding: number = 40
): Viewport {
  if (!points.length) return IDENTITY;
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
  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);
  const availW = Math.max(1, width - 2 * padding);
  const availH = Math.max(1, height - 2 * padding);
  let scale = Math.min(availW / spanX, availH / spanY, MAX_FIT_SCALE);
  scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  return { scale, tx: width / 2 - cx * scale, ty: height / 2 - cy * scale };
}

/** Centra el punto de MUNDO (wx, wy) en el canvas, sin cambiar la escala. */
export function centerOn(
  vp: Viewport,
  wx: number,
  wy: number,
  width: number,
  height: number
): Viewport {
  return { scale: vp.scale, tx: width / 2 - wx * vp.scale, ty: height / 2 - wy * vp.scale };
}

/** Zoom anclado al centro del canvas (para los botones + / −). */
export function zoomAtCenter(
  vp: Viewport,
  factor: number,
  width: number,
  height: number
): Viewport {
  return zoomAt(vp, factor, width / 2, height / 2);
}

// ── Labels sin solapamiento ──────────────────────────────────────────────────

export interface LabelCandidate {
  /** id del nodo (para lookups del caller) */
  id: string;
  /** posición en PANTALLA del ancla del label (a la derecha del nodo) */
  x: number;
  y: number;
  /** ancho estimado del label en px de pantalla */
  width: number;
  /** alto del label en px */
  height: number;
  /** mayor prioridad = se dibuja antes (hover/selected > hubs > resto) */
  priority: number;
}

interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
}

/**
 * Greedy determinista: ordena por prioridad desc (empate: id asc) y acepta cada
 * label cuyo rect no pise ninguno ya aceptado. Devuelve el Set de ids a dibujar.
 * `maxLabels` acota el total (legibilidad en grafos densos).
 */
export function pickVisibleLabels(
  candidates: LabelCandidate[],
  maxLabels: number = 40
): Set<string> {
  const sorted = [...candidates].sort(
    (a, b) => b.priority - a.priority || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
  const accepted: Rect[] = [];
  const out = new Set<string>();
  for (const c of sorted) {
    if (out.size >= maxLabels) break;
    const rect: Rect = {
      x0: c.x,
      y0: c.y - c.height / 2,
      x1: c.x + c.width,
      y1: c.y + c.height / 2,
    };
    if (accepted.some((r) => overlaps(r, rect))) continue;
    accepted.push(rect);
    out.add(c.id);
  }
  return out;
}

/** Ancho estimado de un texto en px (aprox mono-métrica; suficiente para colisiones). */
export function estimateLabelWidth(text: string, fontPx: number = 11): number {
  return Math.max(8, text.length * fontPx * 0.58) + 8; // + padding del pill
}

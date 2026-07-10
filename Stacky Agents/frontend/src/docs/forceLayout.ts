/**
 * forceLayout.ts — Plan 111 F2.
 *
 * Toda la matemática del graph view aislada en un módulo PURO (sin canvas, sin React,
 * sin Math.random): inicialización determinista, un `stepLayout` de
 * repulsión+resortes+centrado con clamp de bordes, y un `staticLayout` para el modo
 * degradado (>300 nodos o prefers-reduced-motion). Testeable con vitest sin DOM.
 */
import type { DocGraphResponse } from "./docGraphModel";

export const MAX_ANIMATED_NODES = 300;

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  group: string;
}

/** índices en el array de nodos (no ids). */
export interface LayoutEdge {
  source: number;
  target: number;
  stale: boolean;
}

export interface LayoutState {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  width: number;
  height: number;
  animated: boolean;
}

// ── Constantes de simulación (cerradas por el plan) ──────────────────────────
const SPRING_LENGTH = 78;
const SPRING_K = 0.08;
const CENTER_K = 0.0016;
const DAMPING = 0.86;
const REPULSION = 1400;
const REP_CUTOFF_SQ = 40000; // solo pares a distancia² < 40000

/** Radio de nodo a partir del in_degree (backlinks): 4 + min(11, inDeg*1.15). */
export function nodeRadius(inDegree: number): number {
  return 4 + Math.min(11, inDegree * 1.15);
}

function seedOf(id: string): number {
  let s = 0;
  for (let i = 0; i < id.length; i++) s += id.charCodeAt(i);
  return s;
}

function frac(v: number): number {
  return v - Math.floor(v);
}

/** Grupo de color/columna: notas por fuente, código y faltantes por su kind. */
function groupOf(kind: string, sourceId: string): string {
  return kind === "note" ? "note:" + (sourceId || "") : kind;
}

/**
 * Construye el estado inicial desde el grafo (109). radio = f(in_degree). Posiciones
 * sembradas deterministas (hash del id, sin Math.random) para reproducibilidad.
 * animated = nodes.length <= MAX_ANIMATED_NODES && !reducedMotion.
 */
export function initLayout(
  graph: DocGraphResponse,
  width: number,
  height: number,
  reducedMotion: boolean
): LayoutState {
  const gnodes = graph?.nodes ?? [];
  const idToIndex = new Map<string, number>();
  const nodes: LayoutNode[] = gnodes.map((n, i) => {
    idToIndex.set(n.id, i);
    const seed = seedOf(n.id);
    return {
      id: n.id,
      x: width * (0.15 + 0.7 * frac(seed * 0.618)),
      y: height * (0.15 + 0.7 * frac(seed * 0.377)),
      vx: 0,
      vy: 0,
      r: nodeRadius(n.in_degree || 0),
      group: groupOf(n.kind, n.source_id),
    };
  });

  const edges: LayoutEdge[] = [];
  for (const e of graph?.edges ?? []) {
    const s = idToIndex.get(e.source);
    const t = idToIndex.get(e.target);
    if (s === undefined || t === undefined || s === t) continue;
    edges.push({ source: s, target: t, stale: Boolean((e as any).stale) });
  }

  const animated = nodes.length <= MAX_ANIMATED_NODES && !reducedMotion;
  return { nodes, edges, width, height, animated };
}

/**
 * Un paso de simulación in-place: repulsión O(n²) acotada, resortes por arista,
 * atracción al centro, damping y clamp de bordes. Devuelve la energía (suma de v²)
 * para detectar convergencia.
 */
export function stepLayout(state: LayoutState): number {
  const { nodes, edges, width, height } = state;
  const n = nodes.length;
  const fx = new Float64Array(n);
  const fy = new Float64Array(n);
  const cx = width / 2;
  const cy = height / 2;

  // Repulsión entre pares acotada por distancia².
  for (let i = 0; i < n; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < n; j++) {
      const b = nodes[j];
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      let d2 = dx * dx + dy * dy;
      if (d2 >= REP_CUTOFF_SQ) continue;
      if (d2 < 0.01) {
        // superpuestos: empujar con un desplazamiento determinista mínimo
        dx = (i - j) || 1;
        dy = 1;
        d2 = dx * dx + dy * dy;
      }
      const d = Math.sqrt(d2);
      const f = REPULSION / d2;
      const ux = dx / d;
      const uy = dy / d;
      fx[i] += ux * f;
      fy[i] += uy * f;
      fx[j] -= ux * f;
      fy[j] -= uy * f;
    }
  }

  // Resortes por arista (longitud natural SPRING_LENGTH).
  for (const e of edges) {
    const a = nodes[e.source];
    const b = nodes[e.target];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const diff = (d - SPRING_LENGTH) * SPRING_K;
    const ux = dx / d;
    const uy = dy / d;
    fx[e.source] += ux * diff;
    fy[e.source] += uy * diff;
    fx[e.target] -= ux * diff;
    fy[e.target] -= uy * diff;
  }

  // Atracción al centro + integración + damping + clamp de bordes.
  let energy = 0;
  for (let i = 0; i < n; i++) {
    const node = nodes[i];
    fx[i] += (cx - node.x) * CENTER_K;
    fy[i] += (cy - node.y) * CENTER_K;

    node.vx = (node.vx + fx[i]) * DAMPING;
    node.vy = (node.vy + fy[i]) * DAMPING;
    node.x += node.vx;
    node.y += node.vy;

    // (C3) Clamp de bordes: si se clampea un eje, su velocidad se anula.
    const minX = node.r;
    const maxX = width - node.r;
    const minY = node.r;
    const maxY = height - node.r;
    if (node.x < minX) {
      node.x = minX;
      node.vx = 0;
    } else if (node.x > maxX) {
      node.x = maxX;
      node.vx = 0;
    }
    if (node.y < minY) {
      node.y = minY;
      node.vy = 0;
    } else if (node.y > maxY) {
      node.y = maxY;
      node.vy = 0;
    }

    energy += node.vx * node.vx + node.vy * node.vy;
  }

  return energy;
}

/**
 * Layout determinístico sin animación: distribuye por grupo en columnas + jitter por
 * hash. Se usa si !state.animated (>300 nodos o reduced-motion). x depende solo del
 * grupo (misma columna por grupo); y por posición dentro del grupo con jitter estable.
 */
export function staticLayout(state: LayoutState): void {
  const { nodes, width, height } = state;
  const groups = Array.from(new Set(nodes.map((n) => n.group))).sort();
  const colIndex = new Map<string, number>();
  groups.forEach((g, i) => colIndex.set(g, i));
  const numGroups = groups.length || 1;

  // agrupar índices por grupo, ordenados por id (determinismo).
  const byGroup = new Map<string, LayoutNode[]>();
  for (const n of nodes) {
    const arr = byGroup.get(n.group) ?? [];
    arr.push(n);
    byGroup.set(n.group, arr);
  }

  for (const [g, arr] of byGroup) {
    arr.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const col = colIndex.get(g) ?? 0;
    const x = width * ((col + 1) / (numGroups + 1));
    const count = arr.length;
    arr.forEach((node, row) => {
      const jitter = (frac(seedOf(node.id) * 0.618) - 0.5) * 6;
      node.x = x;
      node.y = height * ((row + 1) / (count + 1)) + jitter;
      node.vx = 0;
      node.vy = 0;
    });
  }
}

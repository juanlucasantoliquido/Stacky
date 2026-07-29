/**
 * graphViewport.test.ts — tests puros (sin jsdom) del zoom/pan y labels del grafo.
 */
import { describe, it, expect } from "vitest";
import {
  IDENTITY,
  MIN_SCALE,
  MAX_SCALE,
  zoomAt,
  panBy,
  toWorld,
  toScreen,
  pickVisibleLabels,
  estimateLabelWidth,
  // Plan 268 F0.4 — matemática de encuadre / zoom al centro
  ZOOM_STEP,
  MAX_FIT_SCALE,
  fitViewport,
  centerOn,
  zoomAtCenter,
  type Viewport,
  type LabelCandidate,
} from "./graphViewport";
import { initLayout, stepLayout } from "./forceLayout";
import type { DocGraphResponse } from "./docGraphModel";

describe("viewport: transformaciones mundo↔pantalla", () => {
  it("identidad: toScreen == identidad", () => {
    expect(toScreen(IDENTITY, 10, 20)).toEqual({ x: 10, y: 20 });
    expect(toWorld(IDENTITY, 10, 20)).toEqual({ x: 10, y: 20 });
  });

  it("toWorld invierte a toScreen para cualquier viewport", () => {
    const vp: Viewport = { scale: 2.5, tx: -37, ty: 12 };
    const p = toScreen(vp, 41.5, -8.25);
    const back = toWorld(vp, p.x, p.y);
    expect(back.x).toBeCloseTo(41.5, 10);
    expect(back.y).toBeCloseTo(-8.25, 10);
  });
});

describe("zoomAt", () => {
  it("mantiene fijo el punto del mundo bajo el cursor", () => {
    const vp: Viewport = { scale: 1, tx: 0, ty: 0 };
    const cursor = { x: 120, y: 80 };
    const worldBefore = toWorld(vp, cursor.x, cursor.y);
    const zoomed = zoomAt(vp, 1.6, cursor.x, cursor.y);
    const worldAfter = toWorld(zoomed, cursor.x, cursor.y);
    expect(worldAfter.x).toBeCloseTo(worldBefore.x, 10);
    expect(worldAfter.y).toBeCloseTo(worldBefore.y, 10);
    expect(zoomed.scale).toBeCloseTo(1.6, 10);
  });

  it("clampea la escala en [MIN_SCALE, MAX_SCALE]", () => {
    let vp: Viewport = IDENTITY;
    for (let i = 0; i < 50; i++) vp = zoomAt(vp, 1.5, 0, 0);
    expect(vp.scale).toBe(MAX_SCALE);
    for (let i = 0; i < 100; i++) vp = zoomAt(vp, 0.5, 0, 0);
    expect(vp.scale).toBe(MIN_SCALE);
  });

  it("en el clamp devuelve el mismo objeto (no muta tx/ty)", () => {
    const vp: Viewport = { scale: MAX_SCALE, tx: 5, ty: 7 };
    expect(zoomAt(vp, 2, 100, 100)).toBe(vp);
  });
});

describe("panBy", () => {
  it("traslada en pantalla sin cambiar la escala", () => {
    const vp = panBy({ scale: 2, tx: 10, ty: -4 }, 5, 6);
    expect(vp).toEqual({ scale: 2, tx: 15, ty: 2 });
  });
});

describe("pickVisibleLabels", () => {
  const mk = (id: string, x: number, y: number, priority: number): LabelCandidate => ({
    id,
    x,
    y,
    width: 60,
    height: 14,
    priority,
  });

  it("acepta labels que no se pisan", () => {
    const out = pickVisibleLabels([mk("a", 0, 0, 1), mk("b", 0, 40, 1), mk("c", 100, 0, 1)]);
    expect(out).toEqual(new Set(["a", "b", "c"]));
  });

  it("ante solape gana la prioridad más alta", () => {
    const out = pickVisibleLabels([mk("bajo", 0, 0, 1), mk("alto", 10, 4, 9)]);
    expect(out.has("alto")).toBe(true);
    expect(out.has("bajo")).toBe(false);
  });

  it("empate de prioridad: desempata determinista por id", () => {
    const out1 = pickVisibleLabels([mk("b", 0, 0, 1), mk("a", 5, 2, 1)]);
    const out2 = pickVisibleLabels([mk("a", 5, 2, 1), mk("b", 0, 0, 1)]);
    expect(out1).toEqual(out2);
    expect(out1.has("a")).toBe(true);
  });

  it("respeta maxLabels", () => {
    const many = Array.from({ length: 30 }, (_, i) => mk(`n${i}`, i * 100, 0, 1));
    expect(pickVisibleLabels(many, 5).size).toBe(5);
  });
});

describe("estimateLabelWidth", () => {
  it("crece con el largo del texto y nunca es 0", () => {
    expect(estimateLabelWidth("")).toBeGreaterThan(0);
    expect(estimateLabelWidth("nota-larga.md")).toBeGreaterThan(estimateLabelWidth("a"));
  });
});

// ── Plan 268 F0.4 — encuadre determinista, centrado y zoom al centro ─────────

const W = 800;
const H = 600;
const PAD = 40;

function within(v: number, lo: number, hi: number): boolean {
  return v >= lo && v <= hi;
}

describe("plan 268 F0.4: fitViewport / centerOn / zoomAtCenter", () => {
  it("fitViewport con lista vacia devuelve IDENTITY", () => {
    expect(fitViewport([], W, H)).toBe(IDENTITY);
  });

  it("fitViewport con un solo punto centra y no supera MAX_FIT_SCALE", () => {
    const vp = fitViewport([{ x: 123, y: 456 }], W, H);
    expect(vp.scale).toBeLessThanOrEqual(MAX_FIT_SCALE);
    expect(vp.scale).toBeLessThanOrEqual(MAX_SCALE);
    const p = toScreen(vp, 123, 456);
    expect(p.x).toBeCloseTo(W / 2, 6);
    expect(p.y).toBeCloseTo(H / 2, 6);
  });

  it("fitViewport deja todos los puntos dentro del canvas con padding", () => {
    const pts = Array.from({ length: 500 }, (_, i) => ({
      x: (i * 37) % 800,
      y: (i * 53) % 600,
    }));
    const vp = fitViewport(pts, W, H, PAD);
    for (const p of pts) {
      const s = toScreen(vp, p.x, p.y);
      expect(within(s.x, PAD - 1, W - PAD + 1)).toBe(true);
      expect(within(s.y, PAD - 1, H - PAD + 1)).toBe(true);
    }
  });

  it("fitViewport clampea la escala a MIN_SCALE con un grafo gigantesco", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 100000, y: 100000 },
    ];
    const vp = fitViewport(pts, W, H, PAD);
    expect(vp.scale).toBe(MIN_SCALE);
  });

  it("fitViewport incluye el radio de cada punto en el bounding box", () => {
    // Span elegido a proposito para que las DOS escalas caigan ESTRICTAMENTE
    // entre MIN_SCALE y MAX_FIT_SCALE: con spans chicos las dos se clampean
    // arriba y con spans enormes las dos se clampean abajo — en ambos casos el
    // caso no mediria nada (falso verde).
    const sinR = fitViewport([{ x: 0, y: 0 }, { x: 1000, y: 1000 }], W, H, PAD);
    const conR = fitViewport(
      [{ x: 0, y: 0, r: 100 }, { x: 1000, y: 1000, r: 100 }],
      W,
      H,
      PAD
    );
    expect(sinR.scale).toBeLessThan(MAX_FIT_SCALE);
    expect(sinR.scale).toBeGreaterThan(MIN_SCALE);
    expect(conR.scale).toBeGreaterThan(MIN_SCALE);
    expect(conR.scale).toBeLessThan(sinR.scale);
  });

  it("centerOn deja el punto del mundo en el centro de la pantalla", () => {
    const vp: Viewport = { scale: 2.5, tx: -321, ty: 99 };
    const next = centerOn(vp, 40, 70, W, H);
    expect(next.scale).toBe(2.5);
    const p = toScreen(next, 40, 70);
    expect(p.x).toBeCloseTo(W / 2, 6);
    expect(p.y).toBeCloseTo(H / 2, 6);
  });

  it("zoomAtCenter mantiene fijo el punto del mundo bajo el centro", () => {
    const vp: Viewport = { scale: 1, tx: 0, ty: 0 };
    const before = toWorld(vp, W / 2, H / 2);
    const next = zoomAtCenter(vp, ZOOM_STEP, W, H);
    const after = toWorld(next, W / 2, H / 2);
    expect(next.scale).toBeCloseTo(ZOOM_STEP, 10);
    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });

  it("ZOOM_STEP aplicado y luego su inverso vuelve al viewport original", () => {
    const vp: Viewport = { scale: 1, tx: 12, ty: -34 };
    const zoomed = zoomAtCenter(vp, ZOOM_STEP, W, H);
    const back = zoomAtCenter(zoomed, 1 / ZOOM_STEP, W, H);
    expect(back.scale).toBeCloseTo(vp.scale, 10);
    expect(back.tx).toBeCloseTo(vp.tx, 6);
    expect(back.ty).toBeCloseTo(vp.ty, 6);
  });

  it("fitViewport sobre las posiciones de un LayoutState deja todos los nodos visibles", () => {
    const nodes = Array.from({ length: 50 }, (_, i) => ({
      id: `n${i}`,
      kind: "note" as const,
      label: `n${i}.md`,
      path: `docs/n${i}.md`,
      source_id: "s1",
      in_degree: i % 5,
      out_degree: 1,
      has_frontmatter: false,
      exists: true,
    }));
    const graph: DocGraphResponse = {
      ok: true,
      generated_at: "2026-07-29T00:00:00+00:00",
      active_project: "TEST",
      sources: [],
      nodes,
      edges: nodes.slice(1).map((n, i) => ({
        source: nodes[i].id,
        target: n.id,
        kind: "md" as const,
      })),
      orphans: [],
      stats: {},
      doc_health: null,
    };
    const state = initLayout(graph, W, H, false);
    for (let i = 0; i < 100; i++) stepLayout(state);
    const vp = fitViewport(
      state.nodes.map((n) => ({ x: n.x, y: n.y, r: n.r })),
      W,
      H,
      PAD
    );
    for (const n of state.nodes) {
      const s = toScreen(vp, n.x, n.y);
      expect(within(s.x, PAD - 1 - n.r * vp.scale, W - PAD + 1 + n.r * vp.scale)).toBe(true);
      expect(within(s.y, PAD - 1 - n.r * vp.scale, H - PAD + 1 + n.r * vp.scale)).toBe(true);
    }
  });
});

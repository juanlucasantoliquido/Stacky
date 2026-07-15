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
  type Viewport,
  type LabelCandidate,
} from "./graphViewport";

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

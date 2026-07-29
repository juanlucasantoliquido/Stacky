/**
 * graphMinimap.test.ts — Plan 268 F7.1. Tests PUROS del minimapa y del LOD.
 */
import { describe, it, expect } from "vitest";
import {
  boundsOf,
  minimapTransform,
  viewportRectInMinimap,
  viewportFromMinimapClick,
  shouldDrawEdge,
  LOD_SCALE_THRESHOLD,
  LOD_MIN_RADIUS,
} from "./graphMinimap";
import { IDENTITY, toScreen, type Viewport } from "./graphViewport";
import { nodeRadius } from "./forceLayout";

const MM_W = 160;
const MM_H = 110;
const CANVAS_W = 800;
const CANVAS_H = 600;

describe("boundsOf (plan 268 F7.1)", () => {
  it("boundsOf con lista vacia devuelve ceros", () => {
    expect(boundsOf([])).toEqual({ minX: 0, minY: 0, maxX: 0, maxY: 0 });
  });

  it("boundsOf incluye el radio de cada punto", () => {
    expect(boundsOf([{ x: 10, y: 20, r: 5 }])).toEqual({
      minX: 5,
      minY: 15,
      maxX: 15,
      maxY: 25,
    });
  });
});

describe("minimapTransform (plan 268 F7.1)", () => {
  it("minimapTransform preserva el aspect ratio", () => {
    // un mundo cuadrado en un minimapa apaisado: una sola escala para los dos ejes
    const t = minimapTransform({ minX: 0, minY: 0, maxX: 1000, maxY: 1000 }, MM_W, MM_H);
    const dx = 500 * t.scale;
    const dy = 500 * t.scale;
    expect(dx).toBeCloseTo(dy, 10);
    expect(t.width).toBe(MM_W);
    expect(t.height).toBe(MM_H);
  });

  it("minimapTransform con un solo punto no divide por cero", () => {
    const t = minimapTransform({ minX: 7, minY: 7, maxX: 7, maxY: 7 }, MM_W, MM_H);
    expect(Number.isFinite(t.scale)).toBe(true);
    expect(Number.isFinite(t.offsetX)).toBe(true);
    expect(Number.isFinite(t.offsetY)).toBe(true);
    expect(t.scale).toBeGreaterThan(0);
  });

  it("minimapTransform centra el contenido dentro del minimapa", () => {
    const b = { minX: 0, minY: 0, maxX: 1000, maxY: 1000 };
    const t = minimapTransform(b, MM_W, MM_H);
    const cx = ((b.minX + b.maxX) / 2) * t.scale + t.offsetX;
    const cy = ((b.minY + b.maxY) / 2) * t.scale + t.offsetY;
    expect(cx).toBeCloseTo(MM_W / 2, 6);
    expect(cy).toBeCloseTo(MM_H / 2, 6);
  });

  it("minimapTransform nunca AMPLIA (un mundo diminuto no se agranda)", () => {
    const t = minimapTransform({ minX: 0, minY: 0, maxX: 2, maxY: 2 }, MM_W, MM_H);
    expect(t.scale).toBeLessThanOrEqual(1);
  });
});

describe("viewportRectInMinimap (plan 268 F7.1)", () => {
  const b = { minX: 0, minY: 0, maxX: CANVAS_W, maxY: CANVAS_H };
  const t = minimapTransform(b, MM_W, MM_H);

  it("viewportRectInMinimap devuelve el minimapa entero cuando el viewport abarca todo", () => {
    // A escala 1 y sin traslación el canvas muestra [0,800]x[0,600], que es todo el
    // mundo ⇒ el rect cubre exactamente el AREA DE CONTENIDO del minimapa. No arranca
    // en 0: el minimapa aplica padding y centra preservando el aspect ratio (aca sobra
    // ancho, así que hay franjas a los costados). Se compara contra la transformación,
    // no contra un 0 hardcodeado.
    const r = viewportRectInMinimap(IDENTITY, CANVAS_W, CANVAS_H, t);
    expect(r.x).toBeCloseTo(t.offsetX, 6);
    expect(r.y).toBeCloseTo(t.offsetY, 6);
    expect(r.w).toBeCloseTo((b.maxX - b.minX) * t.scale, 6);
    expect(r.h).toBeCloseTo((b.maxY - b.minY) * t.scale, 6);
  });

  it("viewportRectInMinimap se achica al acercar el zoom", () => {
    const wide = viewportRectInMinimap(IDENTITY, CANVAS_W, CANVAS_H, t);
    const zoomed: Viewport = { scale: 3, tx: -300, ty: -200 };
    const tight = viewportRectInMinimap(zoomed, CANVAS_W, CANVAS_H, t);
    expect(tight.w).toBeLessThan(wide.w);
    expect(tight.h).toBeLessThan(wide.h);
  });

  it("viewportRectInMinimap queda clampeado dentro del minimapa", () => {
    const far: Viewport = { scale: 0.5, tx: 5000, ty: 5000 };
    const r = viewportRectInMinimap(far, CANVAS_W, CANVAS_H, t);
    expect(r.x).toBeGreaterThanOrEqual(0);
    expect(r.y).toBeGreaterThanOrEqual(0);
    expect(r.x + r.w).toBeLessThanOrEqual(MM_W + 1e-9);
    expect(r.y + r.h).toBeLessThanOrEqual(MM_H + 1e-9);
  });

  it("viewportRectInMinimap nunca devuelve ancho o alto negativos", () => {
    for (const vp of [
      IDENTITY,
      { scale: 0.3, tx: -9999, ty: -9999 },
      { scale: 5, tx: 9999, ty: 9999 },
    ] as Viewport[]) {
      const r = viewportRectInMinimap(vp, CANVAS_W, CANVAS_H, t);
      expect(r.w).toBeGreaterThanOrEqual(0);
      expect(r.h).toBeGreaterThanOrEqual(0);
    }
  });
});

describe("viewportFromMinimapClick (plan 268 F7.1)", () => {
  const t = minimapTransform({ minX: 0, minY: 0, maxX: 2000, maxY: 1500 }, MM_W, MM_H);

  it("viewportFromMinimapClick centra el punto clickeado y conserva la escala", () => {
    const vp: Viewport = { scale: 2, tx: 13, ty: -7 };
    const mx = 100;
    const my = 60;
    const next = viewportFromMinimapClick(vp, mx, my, t, CANVAS_W, CANVAS_H);
    expect(next.scale).toBe(2);
    // el punto del mundo que estaba bajo (mx,my) queda en el centro del canvas
    const wx = (mx - t.offsetX) / t.scale;
    const wy = (my - t.offsetY) / t.scale;
    const p = toScreen(next, wx, wy);
    expect(p.x).toBeCloseTo(CANVAS_W / 2, 6);
    expect(p.y).toBeCloseTo(CANVAS_H / 2, 6);
  });

  it("viewportFromMinimapClick en una esquina no rompe el viewport", () => {
    for (const [mx, my] of [
      [0, 0],
      [MM_W, 0],
      [0, MM_H],
      [MM_W, MM_H],
    ]) {
      const next = viewportFromMinimapClick(IDENTITY, mx, my, t, CANVAS_W, CANVAS_H);
      expect(Number.isFinite(next.tx)).toBe(true);
      expect(Number.isFinite(next.ty)).toBe(true);
      expect(next.scale).toBe(IDENTITY.scale);
    }
  });
});

describe("shouldDrawEdge — nivel de detalle (plan 268 F7.1, C13)", () => {
  it("shouldDrawEdge devuelve true a escala normal aunque los dos nodos sean chicos", () => {
    expect(shouldDrawEdge(4, 4, 1)).toBe(true);
    expect(shouldDrawEdge(4, 4, LOD_SCALE_THRESHOLD)).toBe(true);
  });

  it("shouldDrawEdge oculta la arista entre dos nodos de radio menor a 6 al alejar", () => {
    expect(shouldDrawEdge(5, 5.9, 0.4)).toBe(false);
  });

  it("shouldDrawEdge conserva la arista si al menos un extremo es un hub", () => {
    expect(shouldDrawEdge(5, LOD_MIN_RADIUS, 0.4)).toBe(true);
    expect(shouldDrawEdge(12, 4, 0.4)).toBe(true);
  });

  it("shouldDrawEdge con los radios que produce nodeRadius oculta exactamente in_degree<=1", () => {
    // El umbral queda atado al modelo REAL de forceLayout, no a un número inventado.
    expect(nodeRadius(0)).toBeLessThan(LOD_MIN_RADIUS);
    expect(nodeRadius(1)).toBeLessThan(LOD_MIN_RADIUS);
    expect(nodeRadius(2)).toBeGreaterThanOrEqual(LOD_MIN_RADIUS);
    const far = 0.4;
    expect(shouldDrawEdge(nodeRadius(1), nodeRadius(1), far)).toBe(false);
    expect(shouldDrawEdge(nodeRadius(1), nodeRadius(2), far)).toBe(true);
    expect(shouldDrawEdge(nodeRadius(2), nodeRadius(2), far)).toBe(true);
  });
});

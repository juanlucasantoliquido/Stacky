// Plan 174 F1 — Ventana de virtualización (lógica pura).
import { describe, it, expect } from "vitest";
import {
  computeVirtualWindow,
  deriveIsVirtualized,
  shouldVirtualize,
  VIRTUALIZATION_THRESHOLD,
} from "../virtualWindow";

const BASE = { rowHeightPx: 22, viewportHeightPx: 600, scrollTopPx: 0 };

describe("computeVirtualWindow", () => {
  it("lista vacía no renderiza nada ni deja spacers", () => {
    expect(computeVirtualWindow({ ...BASE, total: 0 })).toEqual({
      start: 0,
      end: 0,
      padTopPx: 0,
      padBottomPx: 0,
      rendered: 0,
    });
  });

  it("si entra todo en el viewport, se renderiza todo sin spacers", () => {
    const w = computeVirtualWindow({ ...BASE, total: 10, viewportHeightPx: 5000 });

    expect(w.start).toBe(0);
    expect(w.end).toBe(10);
    expect(w.padTopPx).toBe(0);
    expect(w.padBottomPx).toBe(0);
  });

  it("un scroll más allá del final se clampea: nada de índices ni pads negativos", () => {
    const w = computeVirtualWindow({ ...BASE, total: 100, scrollTopPx: 999_999 });

    expect(w.start).toBeGreaterThanOrEqual(0);
    expect(w.end).toBeLessThanOrEqual(100);
    expect(w.padTopPx).toBeGreaterThanOrEqual(0);
    expect(w.padBottomPx).toBeGreaterThanOrEqual(0);
  });

  it("un overscan negativo se trata como 0", () => {
    const conNeg = computeVirtualWindow({ ...BASE, total: 500, scrollTopPx: 2200, overscan: -5 });
    const conCero = computeVirtualWindow({ ...BASE, total: 500, scrollTopPx: 2200, overscan: 0 });

    expect(conNeg).toEqual(conCero);
  });

  it("la fila con foco se incluye aunque esté lejos de la ventana", () => {
    // Si se desmonta la fila enfocada, el navegador manda el foco al body y el
    // operador pierde dónde estaba en la lista.
    const w = computeVirtualWindow({ ...BASE, total: 1000, scrollTopPx: 0, pinnedIndex: 800 });

    expect(w.start).toBeLessThanOrEqual(800);
    expect(w.end).toBeGreaterThan(800);
  });

  it("un pinnedIndex fuera de rango se ignora en vez de romper", () => {
    const w = computeVirtualWindow({ ...BASE, total: 100, pinnedIndex: 5000 });

    expect(w.end).toBeLessThanOrEqual(100);
  });

  it("presupuesto: 5000 filas rinden ≤60 nodos y el alto total se conserva", () => {
    const total = 5000;
    const w = computeVirtualWindow({
      total,
      rowHeightPx: 22,
      viewportHeightPx: 600,
      scrollTopPx: 50_000,
      overscan: 10,
    });

    expect(w.rendered).toBeLessThanOrEqual(60);
    // Si el alto total no se conserva, la barra de scroll salta mientras se usa.
    expect(w.padTopPx + w.rendered * 22 + w.padBottomPx).toBe(total * 22);
  });

  it("invariantes de continuidad en cualquier posición", () => {
    for (const scrollTopPx of [0, 500, 5_000, 44_000, 110_000]) {
      const w = computeVirtualWindow({ total: 5000, rowHeightPx: 22, viewportHeightPx: 600, scrollTopPx });

      expect(w.start).toBeLessThanOrEqual(w.end);
      expect(w.end - w.start).toBe(w.rendered);
      expect(w.padTopPx).toBe(w.start * 22);
      expect(w.padBottomPx).toBe((5000 - w.end) * 22);
    }
  });

  it("altura de fila 0 no divide por cero: devuelve la lista entera", () => {
    const w = computeVirtualWindow({ total: 50, rowHeightPx: 0, viewportHeightPx: 600, scrollTopPx: 0 });

    expect(w).toEqual({ start: 0, end: 50, padTopPx: 0, padBottomPx: 0, rendered: 50 });
  });
});

describe("shouldVirtualize", () => {
  it("por debajo del umbral NO se virtualiza aunque la flag esté ON", () => {
    // Virtualizar una lista corta rompe el Ctrl+F del navegador sin ganar nada.
    expect(shouldVirtualize(150, true)).toBe(false);
  });

  it("por encima del umbral sí", () => {
    expect(shouldVirtualize(201, true)).toBe(true);
  });

  it("justo en el umbral entra", () => {
    expect(shouldVirtualize(VIRTUALIZATION_THRESHOLD, true)).toBe(true);
  });

  it("con la flag apagada nunca, por larga que sea", () => {
    expect(shouldVirtualize(5000, false)).toBe(false);
  });

  it("deriveIsVirtualized es la MISMA decisión: no hay modo sin umbral", () => {
    for (const [t, f] of [[150, true], [201, true], [5000, false]] as [number, boolean][]) {
      expect(deriveIsVirtualized(t, f)).toBe(shouldVirtualize(t, f));
    }
  });
});

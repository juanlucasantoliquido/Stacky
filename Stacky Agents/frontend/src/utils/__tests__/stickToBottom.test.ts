// Plan 174 F2 — Anclaje al fondo del panel de logs.
import { describe, it, expect } from "vitest";
import { isPinnedToBottom, STICK_SLACK_PX } from "../stickToBottom";

describe("isPinnedToBottom", () => {
  it("exactamente al fondo", () => {
    expect(isPinnedToBottom(400, 600, 1000)).toBe(true);
  });

  it("a 39 px del fondo todavía cuenta como al fondo", () => {
    // El scroll no cae en múltiplos exactos de la altura de fila: sin holgura,
    // el autoscroll se cortaría solo por 3 píxeles.
    expect(isPinnedToBottom(361, 600, 1000)).toBe(true);
  });

  it("a 41 px ya no: el operador scrolleó arriba a leer algo", () => {
    expect(isPinnedToBottom(359, 600, 1000)).toBe(false);
  });

  it("contenido más chico que el viewport siempre es fondo", () => {
    expect(isPinnedToBottom(0, 600, 100)).toBe(true);
  });

  it("todo en cero (aún sin montar) no rompe", () => {
    expect(isPinnedToBottom(0, 0, 0)).toBe(true);
  });

  it("la holgura es configurable", () => {
    expect(isPinnedToBottom(0, 600, 1000, 0)).toBe(false);
    expect(isPinnedToBottom(0, 600, 1000, 400)).toBe(true);
    expect(STICK_SLACK_PX).toBe(40);
  });
});

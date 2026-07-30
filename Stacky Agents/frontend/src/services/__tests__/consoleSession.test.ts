/**
 * consoleSession.test.ts — Plan 265 F1.5. 9 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleSession.test.ts
 */
import { describe, it, expect } from "vitest";
import { sessionIdentity, applyPresentation, opensNewSession } from "../consoleSession";
import type { SessionBearingState } from "../consoleSession";
import type { ConsolePresentation } from "../consolePresentation";

const ALL_PRESENTATIONS: ConsolePresentation[] = ["dock", "full", "minimized"];

function stateWith(p: ConsolePresentation, executionId: number | null = 4242): SessionBearingState {
  return {
    codexConsoleExecutionId: executionId,
    codexConsolePresentation: p,
    codexConsoleMinimized: p === "minimized",
  };
}

describe("consoleSession", () => {
  it("1. invariante central: las 9 transiciones conservan el token de sesión", () => {
    for (const from of ALL_PRESENTATIONS) {
      for (const to of ALL_PRESENTATIONS) {
        const s = stateWith(from, 4242);
        const next = applyPresentation(s, to);
        expect(sessionIdentity(next)).toBe(sessionIdentity(s));
      }
    }
  });

  it("2. las 9 transiciones conservan el executionId (nunca null, nunca otro número)", () => {
    for (const from of ALL_PRESENTATIONS) {
      for (const to of ALL_PRESENTATIONS) {
        const s = stateWith(from, 4242);
        const next = applyPresentation(s, to);
        expect(next.codexConsoleExecutionId).toBe(4242);
      }
    }
  });

  it("3. opensNewSession con executionId 4242 es false para los 3 destinos", () => {
    const s = stateWith("dock", 4242);
    for (const to of ALL_PRESENTATIONS) {
      expect(opensNewSession(s, to)).toBe(false);
    }
  });

  it("4. doble apertura de 'full' es idéntica a aplicarlo una vez, y el token no cambió", () => {
    const s = stateWith("dock", 4242);
    const once = applyPresentation(s, "full");
    const twice = applyPresentation(once, "full");
    expect(twice).toEqual(once);
    expect(sessionIdentity(twice)).toBe(sessionIdentity(once));
  });

  it("5. sesión muerta (executionId null): no lanza, opensNewSession true, token estable", () => {
    const s = stateWith("dock", null);
    expect(() => applyPresentation(s, "full")).not.toThrow();
    expect(opensNewSession(s, "full")).toBe(true);
    const t1 = sessionIdentity(s);
    const t2 = sessionIdentity(s);
    expect(t1).toBe(t2);
  });

  it("6. sincronía del legado: 'minimized' -> codexConsoleMinimized true; 'dock'/'full' -> false", () => {
    const s = stateWith("dock", 4242);
    expect(applyPresentation(s, "minimized").codexConsoleMinimized).toBe(true);
    expect(applyPresentation(s, "dock").codexConsoleMinimized).toBe(false);
    expect(applyPresentation(s, "full").codexConsoleMinimized).toBe(false);
  });

  it("7. sessionIdentity NO depende de la presentación", () => {
    const tokens = ALL_PRESENTATIONS.map((p) => sessionIdentity(stateWith(p, 4242)));
    expect(new Set(tokens).size).toBe(1);
  });

  it("8. sessionIdentity SÍ distingue sesiones (obligatorio junto al 7 - anti falso verde)", () => {
    const t1 = sessionIdentity(stateWith("dock", 1));
    const t2 = sessionIdentity(stateWith("dock", 2));
    expect(t1).not.toBe(t2);
  });

  it("9. entrada degenerada (undefined, campos faltantes) no lanza", () => {
    expect(() => sessionIdentity({} as SessionBearingState)).not.toThrow();
    expect(() => applyPresentation({} as SessionBearingState, "full")).not.toThrow();
    expect(() => opensNewSession({} as SessionBearingState, "full")).not.toThrow();
  });
});

/**
 * consolePresentation.test.ts — Plan 265 F1. 11 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consolePresentation.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  normalizePresentation,
  presentationFromLegacy,
  legacyMinimizedFrom,
  togglePresentation,
  hidesAppChrome,
  DEFAULT_PRESENTATION,
} from "../consolePresentation";

describe("consolePresentation", () => {
  it("1. normalizePresentation('full') -> 'full'", () => {
    expect(normalizePresentation("full")).toBe("full");
  });

  it("2. normalizePresentation con basura/undefined/null/42 -> 'dock', nunca lanza", () => {
    expect(normalizePresentation("basura")).toBe("dock");
    expect(normalizePresentation(undefined)).toBe("dock");
    expect(normalizePresentation(null)).toBe("dock");
    expect(normalizePresentation(42)).toBe("dock");
  });

  it("3. presentationFromLegacy(true) -> 'minimized'", () => {
    expect(presentationFromLegacy(true)).toBe("minimized");
  });

  it("4. presentationFromLegacy(false) / (undefined) -> 'dock'", () => {
    expect(presentationFromLegacy(false)).toBe("dock");
    expect(presentationFromLegacy(undefined)).toBe("dock");
  });

  it("5. legacyMinimizedFrom('minimized') -> true", () => {
    expect(legacyMinimizedFrom("minimized")).toBe(true);
  });

  it("6. legacyMinimizedFrom('full') y ('dock') -> false", () => {
    expect(legacyMinimizedFrom("full")).toBe(false);
    expect(legacyMinimizedFrom("dock")).toBe(false);
  });

  it("7. togglePresentation('dock') -> 'full'", () => {
    expect(togglePresentation("dock")).toBe("full");
  });

  it("8. togglePresentation('full') -> 'dock'", () => {
    expect(togglePresentation("full")).toBe("dock");
  });

  it("9. togglePresentation('minimized') -> 'dock'", () => {
    expect(togglePresentation("minimized")).toBe("dock");
  });

  it("10. hidesAppChrome true SOLO para 'full'", () => {
    expect(hidesAppChrome("full")).toBe(true);
    expect(hidesAppChrome("dock")).toBe(false);
    expect(hidesAppChrome("minimized")).toBe(false);
  });

  it("11. round-trip legacyMinimizedFrom(presentationFromLegacy(x)) === x para true/false", () => {
    expect(legacyMinimizedFrom(presentationFromLegacy(true))).toBe(true);
    expect(legacyMinimizedFrom(presentationFromLegacy(false))).toBe(false);
  });

  it("DEFAULT_PRESENTATION es 'dock'", () => {
    expect(DEFAULT_PRESENTATION).toBe("dock");
  });
});

import { describe, it, expect } from "vitest";
import { THEME_STORAGE_KEY, normalizeChoice, resolveTheme } from "../theme";

describe("Plan 141 F0 — clave congelada", () => {
  it("la clave localStorage es exactamente stacky.ui.theme", () => {
    expect(THEME_STORAGE_KEY).toBe("stacky.ui.theme");
  });
});

describe("Plan 141 F0 — normalizeChoice (default dark)", () => {
  it("valores válidos se conservan", () => {
    expect(normalizeChoice("dark")).toBe("dark");
    expect(normalizeChoice("light")).toBe("light");
    expect(normalizeChoice("system")).toBe("system");
  });
  it("null/undefined/vacío/inválido/mayúsculas caen a dark", () => {
    expect(normalizeChoice(null)).toBe("dark");
    expect(normalizeChoice(undefined)).toBe("dark");
    expect(normalizeChoice("")).toBe("dark");
    expect(normalizeChoice("weird")).toBe("dark");
    expect(normalizeChoice("DARK")).toBe("dark"); // case-sensitive a propósito
  });
});

describe("Plan 141 F0 — resolveTheme (byte-idéntico por defecto)", () => {
  it("default es dark AUNQUE el SO prefiera claro (byte-idéntico)", () => {
    expect(resolveTheme(null, false)).toBe("dark");
    expect(resolveTheme(null, true)).toBe("dark");
  });
  it("dark/light explícitos ignoran el SO", () => {
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("light", false)).toBe("light");
  });
  it("system sigue al SO", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});

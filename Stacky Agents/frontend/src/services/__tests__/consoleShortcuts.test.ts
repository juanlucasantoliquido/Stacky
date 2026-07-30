/**
 * consoleShortcuts.test.ts — Plan 265 F6. 10 casos del doc (incluye 3-bis).
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleShortcuts.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  CORE_SHORTCUT_DEFS,
  LIST_NAV_DISPLAY_DEFS,
  detectCollisions,
  comboAllowedInEditable,
  parseCombo,
} from "../shortcuts";
import { CONSOLE_SHORTCUT_DEFS, shouldHandleEscape } from "../consoleShortcuts";

describe("consoleShortcuts", () => {
  it("1. CONSOLE_SHORTCUT_DEFS: cada entrada tiene id/combo/scope/category/description no vacía", () => {
    expect(CONSOLE_SHORTCUT_DEFS.length).toBeGreaterThan(0);
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(d.id).toBeTruthy();
      expect(d.combo).toBeTruthy();
      expect(d.scope).toBeTruthy();
      expect(d.category).toBeTruthy();
      expect(d.description).toBeTruthy();
    }
  });

  it("2. category de todas pertenece a {'global','navegacion','listas'}", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(["global", "navegacion", "listas"]).toContain(d.category);
    }
  });

  it("3. colisiones same-scope con la función real: []", () => {
    const all = [
      ...CORE_SHORTCUT_DEFS,
      ...LIST_NAV_DISPLAY_DEFS,
      ...CONSOLE_SHORTCUT_DEFS,
    ] as Parameters<typeof detectCollisions>[0];
    expect(detectCollisions(all)).toEqual([]);
  });

  it("3-bis. colisiones cross-scope (agrupando SOLO por combo, ignorando scope) están todas declaradas", () => {
    // Mapa congelado de duplicados cross-scope YA conocidos y resueltos, con su
    // motivo en prosa. Un duplicado nuevo no declarado acá hace ROJO este test.
    const _CROSS_SCOPE_RESUELTAS: Record<string, string> = {
      // (vacío hoy: los 3 combos nuevos de la consola — Ctrl+Shift+Enter,
      // Ctrl+Shift+F, Ctrl+Shift+C — no colisionan con ningún combo existente
      // de CORE_SHORTCUT_DEFS ni de LIST_NAV_DISPLAY_DEFS. `Escape` de la
      // consola NO entra a este array: vive en onKeyDown local, D3.)
    };

    const all = [...CORE_SHORTCUT_DEFS, ...LIST_NAV_DISPLAY_DEFS, ...CONSOLE_SHORTCUT_DEFS];
    const byCombo = new Map<string, string[]>();
    for (const d of all) {
      const key = d.combo.toLowerCase();
      byCombo.set(key, [...(byCombo.get(key) || []), d.id]);
    }
    const duplicated = [...byCombo.entries()].filter(([, ids]) => ids.length > 1);
    for (const [combo] of duplicated) {
      expect(_CROSS_SCOPE_RESUELTAS[combo], `combo '${combo}' colisiona cross-scope sin declarar`).toBeDefined();
    }
  });

  it("4. ningún combo es exactamente 'Ctrl+F' (reservado para el navegador)", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(d.combo).not.toBe("Ctrl+F");
    }
  });

  it("5. Enter/Shift+Enter/Escape fuera del registro (viven en onKeyDown locales, D3)", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(["Enter", "Shift+Enter", "Escape"]).not.toContain(d.combo);
    }
  });

  it("6. shouldHandleEscape('full') -> true", () => {
    expect(shouldHandleEscape("full")).toBe(true);
  });

  it("7. shouldHandleEscape('dock') y ('minimized') -> false", () => {
    expect(shouldHandleEscape("dock")).toBe(false);
    expect(shouldHandleEscape("minimized")).toBe(false);
  });

  it("8. shouldHandleEscape con basura -> false, no lanza", () => {
    expect(() => shouldHandleEscape(undefined as never)).not.toThrow();
    expect(shouldHandleEscape(undefined as never)).toBe(false);
    expect(shouldHandleEscape("otra" as never)).toBe(false);
  });

  it("9. [ADICIÓN ARQUITECTO] ratchet de atajos muertos: comboAllowedInEditable === true para TODOS", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(comboAllowedInEditable(d.combo)).toBe(true);
    }
  });

  it("10. ningún combo contiene backtick (tecla muerta en layouts español)", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(d.combo.includes("`")).toBe(false);
    }
  });

  it("(sanidad) parseCombo reconoce los 3 combos nuevos con Ctrl", () => {
    for (const d of CONSOLE_SHORTCUT_DEFS) {
      expect(parseCombo(d.combo).ctrl).toBe(true);
    }
  });
});

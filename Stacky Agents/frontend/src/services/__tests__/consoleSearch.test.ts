/**
 * consoleSearch.test.ts — Plan 265 F5(c). 9 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleSearch.test.ts
 */
import { describe, it, expect } from "vitest";
import { searchLines, nextHit, prevHit } from "../consoleSearch";
import type { LogLine } from "../../types";

function ln(message: string): LogLine {
  return { timestamp: "2026-07-29T00:00:00Z", level: "info", message };
}

describe("consoleSearch", () => {
  it("1. query vacía -> []", () => {
    expect(searchLines([ln("hola mundo")], "")).toEqual([]);
  });

  it("2. sin hits -> []", () => {
    expect(searchLines([ln("hola mundo")], "xyz")).toEqual([]);
  });

  it("3. múltiples hits en una línea", () => {
    const hits = searchLines([ln("git status; git log; git status")], "git");
    expect(hits.length).toBe(3);
  });

  it("4. case-insensitive", () => {
    expect(searchLines([ln("ERROR fatal")], "error").length).toBe(1);
  });

  it("5. caracteres especiales de búsqueda tratados como literales", () => {
    const lines = [ln("precio: 3.99 (oferta) [nuevo]")];
    expect(searchLines(lines, ".*").length).toBe(0); // literal ".*" no aparece
    expect(searchLines(lines, "3.99").length).toBe(1); // "." literal
    expect(searchLines(lines, "(oferta)").length).toBe(1);
    expect(searchLines(lines, "[nuevo]").length).toBe(1);
  });

  it("6. nextHit/prevHit dan la vuelta (wrap-around)", () => {
    const lines = [ln("uno git"), ln("dos git"), ln("tres git")];
    const hits = searchLines(lines, "git");
    expect(hits.length).toBe(3);
    expect(nextHit(hits, 2)).toBe(0); // desde el último, vuelve al principio
    expect(prevHit(hits, 0)).toBe(2); // desde el primero, vuelve al final
  });

  it("7. current: null -> nextHit/prevHit devuelven el primero/último", () => {
    const lines = [ln("a git"), ln("b git")];
    const hits = searchLines(lines, "git");
    expect(nextHit(hits, null)).toBe(0);
    expect(prevHit(hits, null)).toBe(hits.length - 1);
  });

  it("8. 5000 líneas en < 100 ms", () => {
    const lines = Array.from({ length: 5000 }, (_, i) => ln(`linea numero ${i}`));
    const start = performance.now();
    searchLines(lines, "numero");
    expect(performance.now() - start).toBeLessThan(100);
  });

  it("9. una línea de 200000 caracteres sin colgar", () => {
    const huge = ln(`${"x".repeat(200_000)}buscame${"x".repeat(1000)}`);
    const start = performance.now();
    const hits = searchLines([huge], "buscame");
    expect(hits.length).toBe(1);
    expect(performance.now() - start).toBeLessThan(100);
  });

  it("nextHit/prevHit con lista vacía -> null", () => {
    expect(nextHit([], null)).toBeNull();
    expect(prevHit([], 0)).toBeNull();
  });
});

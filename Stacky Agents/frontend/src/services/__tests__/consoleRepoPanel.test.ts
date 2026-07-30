/**
 * consoleRepoPanel.test.ts — Plan 265 F4 (frontend). 6 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
 */
import { describe, it, expect } from "vitest";
import { groupFilesByStatus, shortPath } from "../consoleRepoPanel";

describe("consoleRepoPanel", () => {
  it("1. entrada vacía -> los 5 grupos vacíos, no lanza", () => {
    const g = groupFilesByStatus([]);
    expect(g.modified).toEqual([]);
    expect(g.new).toEqual([]);
    expect(g.deleted).toEqual([]);
    expect(g.untracked).toEqual([]);
    expect(g.otros).toEqual([]);
  });

  it("2. status '??' -> untracked", () => {
    const g = groupFilesByStatus([{ path: "a.txt", status: "??" }]);
    expect(g.untracked.map((f) => f.path)).toEqual(["a.txt"]);
  });

  it("3. status con 'M' -> modified", () => {
    const g = groupFilesByStatus([{ path: "b.py", status: " M" }, { path: "c.py", status: "M " }]);
    expect(g.modified.map((f) => f.path).sort()).toEqual(["b.py", "c.py"]);
  });

  it("4. status con 'A' -> new; status con 'D' -> deleted", () => {
    const g = groupFilesByStatus([{ path: "d.py", status: "A " }, { path: "e.py", status: " D" }]);
    expect(g.new.map((f) => f.path)).toEqual(["d.py"]);
    expect(g.deleted.map((f) => f.path)).toEqual(["e.py"]);
  });

  it("5. status desconocido cae en 'otros', nunca se pierde", () => {
    const g = groupFilesByStatus([{ path: "f.py", status: "UU" }]);
    expect(g.otros.map((f) => f.path)).toEqual(["f.py"]);
    const total = g.modified.length + g.new.length + g.deleted.length + g.untracked.length + g.otros.length;
    expect(total).toBe(1);
  });

  it("6. shortPath elide el medio de una ruta larga y respeta el máximo", () => {
    const long = "backend/services/tools/migrar_mantis_gitlab/adapters/scraping_adapter.py";
    const short = shortPath(long, 30);
    expect(short.length).toBeLessThanOrEqual(30);
    expect(short).toContain("...");
    expect(shortPath("corto.py", 30)).toBe("corto.py");
  });
});

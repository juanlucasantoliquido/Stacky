/**
 * consoleRepoPanel.test.ts — Plan 265 F4 + Plan 293 F5.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
 *
 * Plan 293 F5 REESCRIBIÓ dos casos, no sólo agregó. El caso 5 original se
 * llamaba "status desconocido cae en otros" pero usaba `UU`, que NO es
 * desconocido: es un conflicto. El título mentía y por eso nadie lo miró.
 */
import { describe, it, expect } from "vitest";
import { groupFilesByStatus, shortPath } from "../consoleRepoPanel";
import type { GroupedRepoFiles } from "../consoleRepoPanel";

const CLAVES: Array<keyof GroupedRepoFiles> = [
  "conflictos", "modified", "new", "deleted", "renombrados", "untracked", "otros",
];

function total(g: GroupedRepoFiles): number {
  return CLAVES.reduce((acc, k) => acc + g[k].length, 0);
}

describe("consoleRepoPanel", () => {
  it("1. entrada vacía -> los 7 grupos vacíos, no lanza", () => {
    const g = groupFilesByStatus([]);
    for (const k of CLAVES) expect(g[k]).toEqual([]);
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

  // ── REESCRITO (Plan 293 F5) ───────────────────────────────────────────────
  it("5. 'UU' es CONFLICTO, no desconocido", () => {
    const g = groupFilesByStatus([{ path: "f.py", status: "UU" }]);
    expect(g.conflictos.map((f) => f.path)).toEqual(["f.py"]);
    expect(g.otros).toEqual([]);
    expect(total(g)).toBe(1);
  });

  it("5.b un status REALMENTE desconocido cae en 'otros', nunca se pierde", () => {
    const g = groupFilesByStatus([{ path: "g.py", status: "XY" }]);
    expect(g.otros.map((f) => f.path)).toEqual(["g.py"]);
    expect(total(g)).toBe(1);
  });

  it("6. shortPath elide el medio de una ruta larga y respeta el máximo", () => {
    const long = "backend/services/tools/migrar_mantis_gitlab/adapters/scraping_adapter.py";
    const short = shortPath(long, 30);
    expect(short.length).toBeLessThanOrEqual(30);
    expect(short).toContain("...");
    expect(shortPath("corto.py", 30)).toBe("corto.py");
  });

  // ── NUEVOS (Plan 293 F5) ──────────────────────────────────────────────────
  // Los siete pares de conflicto. Antes de este plan, `AA` salía como "nuevo"
  // y `DD` como "borrado": dos de los tres conflictos se mostraban como si
  // todo estuviera bien.
  const CONFLICTOS = ["DD", "AU", "UD", "UA", "DU", "AA", "UU"];
  for (const par of CONFLICTOS) {
    it(`7.${par} -> conflictos (y NO nuevos ni borrados)`, () => {
      const g = groupFilesByStatus([{ path: "x.py", status: par }]);
      expect(g.conflictos.map((f) => f.path)).toEqual(["x.py"]);
      expect(g.new).toEqual([]);
      expect(g.deleted).toEqual([]);
      expect(g.otros).toEqual([]);
    });
  }

  it("8. 'R ' y 'RM' -> renombrados", () => {
    const g = groupFilesByStatus([{ path: "r1.py", status: "R " }, { path: "r2.py", status: "RM" }]);
    expect(g.renombrados.map((f) => f.path).sort()).toEqual(["r1.py", "r2.py"]);
    expect(g.otros).toEqual([]);
  });

  it("9. regresión: ningún archivo se pierde, cualquiera sea el par", () => {
    const entradas = [
      { path: "1", status: "??" }, { path: "2", status: " M" }, { path: "3", status: "A " },
      { path: "4", status: " D" }, { path: "5", status: "AA" }, { path: "6", status: "R " },
      { path: "7", status: "ZZ" },
    ];
    expect(total(groupFilesByStatus(entradas))).toBe(entradas.length);
  });

  it("10. entrada que no es arreglo no lanza y devuelve los 7 grupos vacíos", () => {
    const g = groupFilesByStatus(null as unknown as []);
    for (const k of CLAVES) expect(g[k]).toEqual([]);
    expect(total(g)).toBe(0);
  });
});

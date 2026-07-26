// Plan 176 F8 — Diff por líneas de definiciones de vistas.
import { describe, it, expect } from "vitest";
import { countChanges, diffLines, lineClass, type LineOp } from "../lineDiff";

function ops(lines: LineOp[] | null): string {
  return (lines ?? []).map((l) => `${l.op}:${l.text}`).join(" ");
}

describe("diffLines", () => {
  it("dos textos iguales son todo equal", () => {
    const d = diffLines("a\nb\nc", "a\nb\nc")!;

    expect(d.every((l) => l.op === "equal")).toBe(true);
    expect(countChanges(d)).toEqual({ added: 0, removed: 0 });
  });

  it("una línea cambiada es del + add", () => {
    const d = diffLines("SELECT 1", "SELECT 2")!;

    expect(ops(d)).toBe("del:SELECT 1 add:SELECT 2");
  });

  it("inserción pura: el resto queda equal", () => {
    const d = diffLines("a\nc", "a\nb\nc")!;

    expect(countChanges(d)).toEqual({ added: 1, removed: 0 });
    expect(d.find((l) => l.op === "add")?.text).toBe("b");
    expect(d.filter((l) => l.op === "equal")).toHaveLength(2);
  });

  it("borrado puro: el resto queda equal", () => {
    const d = diffLines("a\nb\nc", "a\nc")!;

    expect(countChanges(d)).toEqual({ added: 0, removed: 1 });
    expect(d.find((l) => l.op === "del")?.text).toBe("b");
    expect(d.filter((l) => l.op === "equal")).toHaveLength(2);
  });

  it("no normaliza espacios: una sangría distinta ES un cambio", () => {
    // Dos definiciones que difieren en espacios difieren de verdad; ocultarlo
    // haría que el operador no entienda por qué el hash no coincide.
    expect(countChanges(diffLines("  SELECT 1", "SELECT 1")!)).toEqual({ added: 1, removed: 1 });
  });

  it("un lado vacío es todo agregado, y al revés", () => {
    // Un texto vacío ES una línea vacía al splitear por `\n`, así que además de
    // las 2 agregadas aparece esa línea como borrada. El drill-down no llega a
    // este caso: si un lado falta cae al render de dos bloques.
    expect(countChanges(diffLines("", "a\nb")!)).toEqual({ added: 2, removed: 1 });
    expect(countChanges(diffLines("a\nb", "")!)).toEqual({ added: 1, removed: 2 });
  });

  it("por encima del cap devuelve null en vez de colgar el navegador", () => {
    // El LCS es O(n·m): 3001×3001 son 9 millones de celdas.
    const gigante = Array.from({ length: 3001 }, (_, i) => `l${i}`).join("\n");

    expect(diffLines(gigante, "a")).toBeNull();
    expect(diffLines("a", gigante)).toBeNull();
  });

  it("justo en el cap todavía diffea", () => {
    // El límite es exclusivo: 3000 líneas entran.
    const alLimite = Array.from({ length: 3000 }, (_, i) => `l${i}`).join("\n");

    expect(diffLines(alLimite, alLimite)).not.toBeNull();
  });
});

describe("lineClass", () => {
  it("una clase por operación y ninguna para las iguales", () => {
    expect(lineClass("add")).toBe("lineAdd");
    expect(lineClass("del")).toBe("lineDel");
    expect(lineClass("equal")).toBe("");
  });
});

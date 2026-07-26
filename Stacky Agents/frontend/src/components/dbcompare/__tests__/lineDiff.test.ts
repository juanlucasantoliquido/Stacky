// Plan 176 F8 — Diff por líneas de definiciones de vistas.
import { describe, it, expect } from "vitest";
import {
  collapseUnchanged,
  countChanges,
  diffLines,
  lineClass,
} from "../lineDiff";

describe("diffLines", () => {
  it("dos textos iguales no tienen cambios", () => {
    const d = diffLines("a\nb\nc", "a\nb\nc");

    expect(d.every((l) => l.op === "equal")).toBe(true);
    expect(countChanges(d)).toEqual({ added: 0, removed: 0 });
  });

  it("detecta una línea agregada", () => {
    const d = diffLines("a\nc", "a\nb\nc");

    expect(countChanges(d)).toEqual({ added: 1, removed: 0 });
    expect(d.find((l) => l.op === "added")?.text).toBe("b");
  });

  it("detecta una línea borrada", () => {
    const d = diffLines("a\nb\nc", "a\nc");

    expect(countChanges(d)).toEqual({ added: 0, removed: 1 });
    expect(d.find((l) => l.op === "removed")?.text).toBe("b");
  });

  it("una línea modificada es un borrado más un agregado", () => {
    const d = diffLines("SELECT 1", "SELECT 2");

    expect(countChanges(d)).toEqual({ added: 1, removed: 1 });
  });

  it("numera las líneas de cada lado", () => {
    const d = diffLines("a\nb", "a\nX\nb");

    const igualA = d.find((l) => l.text === "a")!;
    expect(igualA.sourceNo).toBe(1);
    expect(igualA.targetNo).toBe(1);

    const agregada = d.find((l) => l.text === "X")!;
    expect(agregada.sourceNo).toBeNull();
    expect(agregada.targetNo).toBe(2);
  });

  it("normaliza CRLF: un cambio de fin de línea no es un cambio real", () => {
    expect(countChanges(diffLines("a\r\nb", "a\nb"))).toEqual({ added: 0, removed: 0 });
  });

  it("origen vacío es todo agregado, y al revés", () => {
    expect(countChanges(diffLines("", "a\nb"))).toEqual({ added: 2, removed: 0 });
    expect(countChanges(diffLines("a\nb", ""))).toEqual({ added: 0, removed: 2 });
  });

  it("ambos vacíos no devuelve nada", () => {
    expect(diffLines(null, undefined)).toEqual([]);
  });

  it("degrada honesto con entradas gigantes en vez de colgar", () => {
    // El LCS es O(n·m): 5000×5000 colgaría el navegador.
    const gigante = Array.from({ length: 2500 }, (_, i) => `l${i}`).join("\n");
    const otro = Array.from({ length: 2500 }, (_, i) => `x${i}`).join("\n");

    const d = diffLines(gigante, otro);

    expect(d.every((l) => l.op !== "equal")).toBe(true);
    expect(countChanges(d)).toEqual({ added: 2500, removed: 2500 });
  });
});

describe("collapseUnchanged", () => {
  it("deja solo el entorno de los cambios", () => {
    const texto = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n");
    const modificado = texto.replace("l10", "CAMBIADA");

    const colapsado = collapseUnchanged(diffLines(texto, modificado), 2);

    expect(colapsado.length).toBeLessThan(20);
    expect(colapsado.some((l) => l.text === "CAMBIADA")).toBe(true);
    expect(colapsado.some((l) => l.text === "l0")).toBe(false);
  });

  it("sin cambios no muestra nada", () => {
    expect(collapseUnchanged(diffLines("a\nb", "a\nb"))).toEqual([]);
  });

  it("no se pasa de los bordes del array", () => {
    const d = diffLines("a", "b");

    expect(() => collapseUnchanged(d, 10)).not.toThrow();
  });
});

describe("lineClass", () => {
  it("una clase por operación", () => {
    expect(lineClass("added")).toBe("lineAdded");
    expect(lineClass("removed")).toBe("lineRemoved");
    expect(lineClass("equal")).toBe("lineEqual");
  });
});

// Plan 176 F8 — Export del diff filtrado.
import { describe, it, expect } from "vitest";
import { csvEscape, exportFilename, mimeFor, toCsv, toJson } from "../diffExport";
import type { DiffItem } from "../dbcompareTypes";
import type { TriageDoc } from "../triageLogic";

function item(over: Partial<DiffItem> = {}): DiffItem {
  return {
    object_type: "table",
    schema: "dbo",
    name: "CLIENTES",
    action: "changed",
    severity: "danger",
    changes: [{ kind: "column_removed", severity: "danger", detail: {} }],
    item_key: "table:dbo.CLIENTES",
    ...over,
  } as DiffItem;
}

const triage: TriageDoc = {
  items: { "table:dbo.CLIENTES": { decision: "excluido", note: "ya migrada" } },
};

describe("csvEscape", () => {
  it("escapa comas, comillas y saltos", () => {
    // Los nombres de objeto de BD pueden traer cualquiera de los tres.
    expect(csvEscape("a,b")).toBe('"a,b"');
    expect(csvEscape('di "hola"')).toBe('"di ""hola"""');
    expect(csvEscape("dos\nlineas")).toBe('"dos\nlineas"');
  });

  it("lo simple queda sin comillas", () => {
    expect(csvEscape("CLIENTES")).toBe("CLIENTES");
  });

  it("null y undefined son vacío, no la palabra 'null'", () => {
    expect(csvEscape(null)).toBe("");
    expect(csvEscape(undefined)).toBe("");
  });
});

describe("toCsv", () => {
  it("tiene encabezado y una fila por ítem", () => {
    const csv = toCsv([item(), item({ name: "OTRA", item_key: "table:dbo.OTRA" })]);
    const lineas = csv.trim().split("\n");

    expect(lineas[0]).toContain("object_type");
    expect(lineas).toHaveLength(3);
  });

  it("incluye la decisión del triage", () => {
    expect(toCsv([item()], triage)).toContain("excluido");
  });

  it("sin triage, la decisión es pendiente", () => {
    expect(toCsv([item()])).toContain("pendiente");
  });

  it("termina en salto de línea", () => {
    // Varias herramientas ignoran la última fila si falta.
    expect(toCsv([item()]).endsWith("\n")).toBe(true);
  });

  it("sin ítems deja solo el encabezado", () => {
    expect(toCsv([]).trim().split("\n")).toHaveLength(1);
  });

  it("un nombre con coma no corre las columnas", () => {
    const csv = toCsv([item({ name: "TABLA, RARA" })]);

    expect(csv).toContain('"TABLA, RARA"');
    expect(csv.trim().split("\n")).toHaveLength(2);
  });
});

describe("toJson", () => {
  it("exporta los campos y la decisión", () => {
    const doc = JSON.parse(toJson([item()], triage));

    expect(doc).toHaveLength(1);
    expect(doc[0].name).toBe("CLIENTES");
    expect(doc[0].changes).toEqual(["column_removed"]);
    expect(doc[0].decision).toBe("excluido");
  });

  it("item_key ausente sale como null, no se inventa", () => {
    const doc = JSON.parse(toJson([item({ item_key: undefined })]));

    expect(doc[0].item_key).toBeNull();
  });

  it("sin ítems es un array vacío válido", () => {
    expect(JSON.parse(toJson([]))).toEqual([]);
  });
});

describe("nombre y mime", () => {
  it("el run_id va en el nombre", () => {
    // Dos exports de corridas distintas no pueden llamarse igual.
    expect(exportFilename("run_a_vs_b", "csv")).toBe("run_a_vs_b-diff.csv");
  });

  it("sanea caracteres que no van en un nombre de archivo", () => {
    expect(exportFilename("run/../x", "json")).toBe("run_.._x-diff.json");
  });

  it("sin run_id no genera un nombre vacío", () => {
    expect(exportFilename("", "csv")).toBe("run-diff.csv");
  });

  it("mime por extensión", () => {
    expect(mimeFor("csv")).toContain("text/csv");
    expect(mimeFor("json")).toContain("application/json");
  });
});

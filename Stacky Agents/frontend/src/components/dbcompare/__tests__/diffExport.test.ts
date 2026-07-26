// Plan 176 F8 — Export del diff filtrado.
import { describe, it, expect } from "vitest";
import { csvEscape, exportFilename, mimeFor, toCsv, toJson } from "../diffExport";
import type { DiffItem } from "../dbcompareTypes";

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

describe("csvEscape", () => {
  it("envuelve comas, comillas y saltos, y duplica la comilla interna", () => {
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
  it("el orden de columnas es literal", () => {
    // Cambiarlo rompe las planillas armadas sobre exports anteriores.
    expect(toCsv([]).split("\r\n")[0]).toBe("object_type,schema,name,action,severity,kinds");
  });

  it("golden: una fila con coma, comilla y salto de línea", () => {
    const csv = toCsv([
      item({
        schema: 'es"quema',
        name: "TABLA, RARA",
        changes: [
          { kind: "dos\nlineas", severity: "warn", detail: {} },
          { kind: "column_added", severity: "info", detail: {} },
        ],
      } as Partial<DiffItem>),
    ]);

    expect(csv).toBe(
      "object_type,schema,name,action,severity,kinds\r\n" +
        'table,"es""quema","TABLA, RARA",changed,danger,"dos\nlineas|column_added"\r\n'
    );
  });

  it("los kinds van unidos por barra", () => {
    const csv = toCsv([
      item({
        changes: [
          { kind: "a", severity: "info", detail: {} },
          { kind: "b", severity: "info", detail: {} },
        ],
      } as Partial<DiffItem>),
    ]);

    expect(csv.split("\r\n")[1]).toContain("a|b");
  });

  it("separa filas con CRLF y termina en CRLF", () => {
    // Varias herramientas ignoran la última fila si falta el cierre.
    const csv = toCsv([item(), item({ name: "OTRA" })]);

    expect(csv.split("\r\n").filter(Boolean)).toHaveLength(3);
    expect(csv.endsWith("\r\n")).toBe(true);
  });

  it("no lleva BOM", () => {
    // Un BOM invisible hace que la primera columna no matchee en un import.
    expect(toCsv([item()]).charCodeAt(0)).not.toBe(0xfeff);
  });

  it("sin ítems deja solo el encabezado", () => {
    expect(toCsv([]).split("\r\n").filter(Boolean)).toHaveLength(1);
  });

  it("un nombre con coma no corre las columnas", () => {
    const csv = toCsv([item({ name: "TABLA, RARA" })]);

    expect(csv.split("\r\n").filter(Boolean)).toHaveLength(2);
  });
});

describe("toJson", () => {
  it("exporta los mismos ítems, sin recortar campos", () => {
    const items = [item(), item({ name: "OTRA" })];
    const doc = JSON.parse(toJson(items));

    expect(doc).toEqual(items);
  });

  it("sin ítems es un array vacío válido", () => {
    expect(JSON.parse(toJson([]))).toEqual([]);
  });
});

describe("nombre y mime", () => {
  it("el run_id va en el nombre", () => {
    // Dos exports de corridas distintas no pueden llamarse igual.
    expect(exportFilename("run_a_vs_b", "csv")).toBe("diff_run_a_vs_b.csv");
    expect(exportFilename("run_a_vs_b", "json")).toBe("diff_run_a_vs_b.json");
  });

  it("sanea caracteres que no van en un nombre de archivo", () => {
    expect(exportFilename("run/../x", "json")).toBe("diff_run_.._x.json");
  });

  it("sin run_id no genera un nombre vacío", () => {
    expect(exportFilename("", "csv")).toBe("diff_run.csv");
  });

  it("mime por extensión", () => {
    expect(mimeFor("csv")).toContain("text/csv");
    expect(mimeFor("json")).toContain("application/json");
  });
});

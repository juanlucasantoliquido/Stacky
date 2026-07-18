// Plan 181 F5 — vitest puro de la lógica de la barra de masking.
import { describe, it, expect } from "vitest";
import {
  collectMaskedTables,
  parseTableKey,
  toggleLabel,
} from "./maskingLogic";

describe("parseTableKey", () => {
  it("parte por el primer punto (schema.tabla)", () => {
    expect(parseTableKey("dbo.RUSUARIOS")).toEqual({ schema: "dbo", table: "RUSUARIOS" });
  });
  it("tabla con punto en el nombre: solo el primer separador cuenta", () => {
    expect(parseTableKey("dbo.RA.RB")).toEqual({ schema: "dbo", table: "RA.RB" });
  });
  it("sin punto: schema vacío", () => {
    expect(parseTableKey("RUSUARIOS")).toEqual({ schema: "", table: "RUSUARIOS" });
  });
});

describe("collectMaskedTables", () => {
  it("vacío -> []", () => {
    expect(collectMaskedTables({})).toEqual([]);
  });

  it("solo junta tablas con masked_columns no vacías, orden estable", () => {
    const tables = {
      "dbo.ZTABLE": { masked_columns: ["TOKEN"], columns: ["ID", "TOKEN"] },
      "dbo.ATABLE": { masked_columns: ["PASSWORD"], columns: ["ID", "PASSWORD"] },
      "dbo.NADA": { masked_columns: [], columns: ["ID"] },
    };
    const got = collectMaskedTables(tables);
    expect(got.map((t) => t.key)).toEqual(["dbo.ATABLE", "dbo.ZTABLE"]);
    expect(got[0]).toEqual({
      key: "dbo.ATABLE", schema: "dbo", table: "ATABLE", maskedColumns: ["PASSWORD"],
    });
  });

  it("ignora entradas de error y tablas sin el campo (flag OFF)", () => {
    const tables = {
      "dbo.ROTA": { error: "boom" },
      "dbo.SINCAMPO": { columns: ["ID"] },
      "dbo.OK": { masked_columns: ["SECRET"] },
    };
    expect(collectMaskedTables(tables).map((t) => t.key)).toEqual(["dbo.OK"]);
  });

  it("filtra masked_columns no-string y descarta si queda vacío", () => {
    const tables = {
      "dbo.MIX": { masked_columns: [1, "PASSWORD", null] },
      "dbo.SOLONUM": { masked_columns: [1, 2] },
    };
    const got = collectMaskedTables(tables);
    expect(got.map((t) => t.key)).toEqual(["dbo.MIX"]);
    expect(got[0].maskedColumns).toEqual(["PASSWORD"]);
  });
});

describe("toggleLabel", () => {
  it("masked -> Revelar; visible -> Ocultar", () => {
    expect(toggleLabel("masked")).toBe("Revelar");
    expect(toggleLabel("visible")).toBe("Ocultar");
  });
});

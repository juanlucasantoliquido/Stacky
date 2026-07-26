// Plan 176 F6 — Preferencias de tabla (lógica pura).
import { describe, it, expect } from "vitest";
import {
  canDefineKey,
  candidateKey,
  parseNaturalKeyInput,
  preselect,
  type PrefsCandidate,
} from "../tablePrefsLogic";

function cand(over: Partial<PrefsCandidate> = {}): PrefsCandidate {
  return { schema: "main", table: "RCONTROLES", comparable: true, ...over };
}

describe("preselect", () => {
  it("tilda las de parámetro y nada más", () => {
    const out = preselect(
      [
        cand({ table: "RCONTROLES", param_table: true }),
        cand({ table: "CLIENTES" }),
        cand({ table: "RMODULOS", param_table: true }),
      ],
      20,
    );

    expect(out).toEqual(["main.RCONTROLES", "main.RMODULOS"]);
  });

  it("no tilda una de parámetro que el backend va a rechazar", () => {
    // Preseleccionar algo no comparable produce un error que nadie pidió.
    const out = preselect([cand({ param_table: true, comparable: false })], 20);

    expect(out).toEqual([]);
  });

  it("respeta el cap y corta en orden alfabético", () => {
    // Con 25 marcadas, las 20 que entran tienen que ser siempre las mismas.
    const muchas = Array.from({ length: 25 }, (_, i) =>
      cand({ table: `T${String(i).padStart(2, "0")}`, param_table: true }),
    );

    const out = preselect(muchas, 20);

    expect(out).toHaveLength(20);
    expect(out[0]).toBe("main.T00");
    expect(out[19]).toBe("main.T19");
  });

  it("el orden no depende del orden de llegada", () => {
    const a = preselect([cand({ table: "B", param_table: true }), cand({ table: "A", param_table: true })], 20);
    const b = preselect([cand({ table: "A", param_table: true }), cand({ table: "B", param_table: true })], 20);

    expect(a).toEqual(b);
  });

  it("cap 0 o lista vacía no rompen", () => {
    expect(preselect([cand({ param_table: true })], 0)).toEqual([]);
    expect(preselect([], 20)).toEqual([]);
  });
});

describe("parseNaturalKeyInput", () => {
  it("separa por coma y limpia espacios", () => {
    expect(parseNaturalKeyInput(" MODULO , CODIGO ")).toEqual(["MODULO", "CODIGO"]);
  });

  it("descarta los vacíos entre comas", () => {
    expect(parseNaturalKeyInput("MODULO,,CODIGO,")).toEqual(["MODULO", "CODIGO"]);
  });

  it("sin columnas usables devuelve null, no una lista vacía", () => {
    // Guardar una clave vacía la borraría sin avisar.
    expect(parseNaturalKeyInput("")).toBeNull();
    expect(parseNaturalKeyInput("  ,  , ")).toBeNull();
  });

  it("un nombre que no es un nombre se rechaza acá, no en el 400", () => {
    expect(parseNaturalKeyInput("MODULO; DROP TABLE x")).toBeNull();
    expect(parseNaturalKeyInput("MODULO,CODIGO-RARO")).toBeNull();
  });

  it("acepta los caracteres que usan Oracle y SQL Server", () => {
    expect(parseNaturalKeyInput("COL_1,COL$2,COL#3")).toEqual(["COL_1", "COL$2", "COL#3"]);
  });
});

describe("canDefineKey", () => {
  it("no se define clave donde ya hay PK", () => {
    expect(canDefineKey(cand({ key_source: "pk" }))).toBe(false);
  });

  it("sí donde no hay con qué comparar", () => {
    expect(canDefineKey(cand({ comparable: false }))).toBe(true);
  });

  it("sí cuando la clave declarada quedó inválida, para corregirla", () => {
    expect(
      canDefineKey(cand({ comparable: false, reason: "natural_key_invalid" })),
    ).toBe(true);
  });

  it("no cuando ya es comparable por una clave natural válida", () => {
    expect(canDefineKey(cand({ comparable: true, key_source: "natural" }))).toBe(false);
  });
});

describe("candidateKey", () => {
  it("schema.tabla", () => {
    expect(candidateKey({ schema: "dbo", table: "CLIENTES" })).toBe("dbo.CLIENTES");
  });
});

import { describe, expect, it } from "vitest";
import type { NormalizePropuestaDto } from "../api/endpoints";
import {
  esSeleccionable,
  itemsParaApply,
  puedeAplicar,
  resumenConfianza,
  seleccionablesPorDefecto,
  textoConfirmacion,
} from "./normalize";

function propuesta(overrides: Partial<NormalizePropuestaDto> = {}): NormalizePropuestaDto {
  return {
    number: 77,
    filename: "77_PLAN_X.md",
    estado_propuesto: "IMPLEMENTADO",
    confianza: "alta",
    aplicable: true,
    evidencia: ["El documento trae su Registro de implementación."],
    linea_a_insertar: "**Estado:** IMPLEMENTADO (normalizado 2026-07-29, Plan 263) — sin veredicto de supervisor",
    insert_after_line: 0,
    sha256_visto: "a".repeat(64),
    resella_ledger: false,
    ...overrides,
  };
}

// ── Caso 1 ───────────────────────────────────────────────────────────────────

describe("seleccionablesPorDefecto", () => {
  it("no preselecciona nada", () => {
    const props = [propuesta({ filename: "a.md" }), propuesta({ filename: "b.md" })];
    expect(seleccionablesPorDefecto(props)).toEqual([]);
  });
});

// ── Caso 2 ───────────────────────────────────────────────────────────────────

describe("resumenConfianza", () => {
  it("cuenta por nivel de confianza", () => {
    const props = [
      propuesta({ confianza: "alta" }),
      propuesta({ confianza: "alta" }),
      propuesta({ confianza: "media" }),
      propuesta({ confianza: "sin_evidencia", aplicable: false, estado_propuesto: null, linea_a_insertar: null }),
    ];
    expect(resumenConfianza(props)).toEqual({ alta: 2, media: 1, sin_evidencia: 1 });
  });
});

// ── Caso 3 ───────────────────────────────────────────────────────────────────

describe("puedeAplicar", () => {
  it("false si la flag está apagada", () => {
    expect(puedeAplicar(false, ["a.md"])).toBe(false);
  });
  it("false si no hay seleccionados", () => {
    expect(puedeAplicar(true, [])).toBe(false);
  });
  it("true si la flag está prendida y hay seleccionados", () => {
    expect(puedeAplicar(true, ["a.md"])).toBe(true);
  });
});

// ── Caso 4 ───────────────────────────────────────────────────────────────────

describe("textoConfirmacion", () => {
  it("contiene la cantidad y la palabra archivos", () => {
    const texto = textoConfirmacion(["a.md", "b.md", "c.md"]);
    expect(texto).toContain("3");
    expect(texto).toContain("archivos");
  });
});

// ── Caso 5 ───────────────────────────────────────────────────────────────────

describe("itemsParaApply", () => {
  it("arma {filename, sha256_visto} sin claves de más y sin perder el sha", () => {
    const props = [propuesta({ filename: "77_PLAN_X.md", sha256_visto: "deadbeef".repeat(8) })];
    const items = itemsParaApply(props, ["77_PLAN_X.md"], {});
    expect(items).toEqual([{ filename: "77_PLAN_X.md", sha256_visto: "deadbeef".repeat(8) }]);
    expect(Object.keys(items[0]).sort()).toEqual(["filename", "sha256_visto"]);
  });

  // ── Caso 6 ─────────────────────────────────────────────────────────────────
  it("excluye una propuesta sin sha256_visto", () => {
    const props = [propuesta({ filename: "77_PLAN_X.md", sha256_visto: "" })];
    const items = itemsParaApply(props, ["77_PLAN_X.md"], {});
    expect(items).toEqual([]);
  });

  // ── Caso 8 ─────────────────────────────────────────────────────────────────
  it("excluye una propuesta sin_evidencia sin estado elegido (la app no manda lo que el servidor rechaza)", () => {
    const props = [
      propuesta({
        filename: "78_PLAN_SINEVIDENCIA.md",
        confianza: "sin_evidencia",
        aplicable: false,
        estado_propuesto: null,
        linea_a_insertar: null,
      }),
    ];
    const items = itemsParaApply(props, ["78_PLAN_SINEVIDENCIA.md"], {});
    expect(items).toEqual([]);

    const itemsConElegido = itemsParaApply(
      props, ["78_PLAN_SINEVIDENCIA.md"], { "78_PLAN_SINEVIDENCIA.md": "PROPUESTO" }
    );
    expect(itemsConElegido).toEqual([
      { filename: "78_PLAN_SINEVIDENCIA.md", sha256_visto: propuesta().sha256_visto, estado_elegido: "PROPUESTO" },
    ]);
  });
});

// ── Caso 7 ───────────────────────────────────────────────────────────────────

describe("esSeleccionable", () => {
  it("false si aplicable=false y no hay elegido", () => {
    const p = propuesta({ aplicable: false });
    expect(esSeleccionable(p, undefined)).toBe(false);
    expect(esSeleccionable(p, null)).toBe(false);
  });

  it("true si aplicable=true (el elegido no importa)", () => {
    const p = propuesta({ aplicable: true });
    expect(esSeleccionable(p, null)).toBe(true);
  });

  it("true si aplicable=false y el elegido está en el vocabulario cerrado", () => {
    const p = propuesta({ aplicable: false });
    expect(esSeleccionable(p, "PROPUESTO")).toBe(true);
    expect(esSeleccionable(p, "IMPLEMENTADO-PARCIAL")).toBe(true);
  });

  it("false si el elegido es vacío o no está en el vocabulario", () => {
    const p = propuesta({ aplicable: false });
    expect(esSeleccionable(p, "")).toBe(false);
    expect(esSeleccionable(p, "LO_QUE_SEA")).toBe(false);
  });
});

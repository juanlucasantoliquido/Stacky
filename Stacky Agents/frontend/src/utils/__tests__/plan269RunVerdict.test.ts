/**
 * Plan 269 F3 + F4 — Tests PUROS de la presentación del veredicto.
 * Sin RTL, sin jsdom: el repo no los tiene instalados.
 * 14 casos: 12 de F3 + 2 de F4.
 */
import { describe, expect, it } from "vitest";

import {
  EVIDENCE_LABELS,
  VERDICT_CAUSE_DETAIL,
  VERDICT_LEVEL_VIEW,
  describeVerdict,
  evidenceSummary,
  matchesVerdictLevel,
  verdictChipTone,
  type RunVerdictPayload,
  type VerdictLevel,
} from "../runVerdict";

const TONOS = ["exito", "atencion", "espera", "error"];

describe("plan 269 F3 — presentación del veredicto", () => {
  it("1. las 9 causas tienen texto", () => {
    expect(Object.keys(VERDICT_CAUSE_DETAIL)).toHaveLength(9);
    for (const [causa, texto] of Object.entries(VERDICT_CAUSE_DETAIL)) {
      expect(texto.trim().length, `causa vacía: ${causa}`).toBeGreaterThan(0);
    }
    // Un run que el humano corto NO cerro mal: decirselo seria mentirle.
    expect(VERDICT_CAUSE_DETAIL.cancelado_por_el_operador).not.toContain("cerró mal");
  });

  it("2. los 3 niveles tienen tono y etiqueta", () => {
    const niveles: VerdictLevel[] = ["exito", "advertencia", "error_real"];
    for (const n of niveles) {
      expect(TONOS).toContain(VERDICT_LEVEL_VIEW[n].tone);
      expect(VERDICT_LEVEL_VIEW[n].label.length).toBeGreaterThan(0);
    }
  });

  it("3. un nivel del futuro no se presenta como exito", () => {
    const v = describeVerdict({ level: "nivel_del_futuro", cause: "x" });
    expect(v?.level).toBe("advertencia");
    expect(v?.tone).toBe("atencion");
  });

  it("4. espera_cuota se pinta con tono espera (y el nivel NO cambia)", () => {
    const v = describeVerdict({ level: "advertencia", cause: "espera_cuota" });
    expect(v?.tone).toBe("espera");
    expect(v?.level).toBe("advertencia");
    // Una causa sin tono propio conserva el del nivel.
    const otra = describeVerdict({ level: "advertencia", cause: "falso_rojo_probable" });
    expect(otra?.tone).toBe("atencion");
  });

  it("5. una causa del futuro muestra el texto crudo", () => {
    expect(describeVerdict({ level: "advertencia", cause: "causa_rara" })?.detail).toBe(
      "causa_rara",
    );
  });

  it("6. null y undefined devuelven null", () => {
    expect(describeVerdict(null)).toBeNull();
    expect(describeVerdict(undefined)).toBeNull();
    expect(describeVerdict({ level: "" } as RunVerdictPayload)).toBeNull();
  });

  it("7. needsOperator es false solo en exito", () => {
    expect(describeVerdict({ level: "exito", cause: "cierre_limpio_con_entrega" })?.needsOperator).toBe(false);
    expect(describeVerdict({ level: "advertencia", cause: "falso_rojo_probable" })?.needsOperator).toBe(true);
    expect(describeVerdict({ level: "error_real", cause: "error_sin_entrega_suficiente" })?.needsOperator).toBe(true);
  });

  it("8. evidenceSummary nombra las 3 categorias", () => {
    const texto = evidenceSummary({
      level: "advertencia",
      cause: "falso_rojo_probable",
      present: ["publicado_en_tracker"],
      absent: ["cambio_en_repo"],
      unknown: ["verificacion_ok"],
    });
    expect(texto).toContain("Se encontró");
    expect(texto).toContain("No hay");
    expect(texto).toContain("No se pudo comprobar");
    expect(texto).toContain(EVIDENCE_LABELS.publicado_en_tracker);
  });

  it("9. evidenceSummary vacio no rompe", () => {
    expect(evidenceSummary({ level: "exito", cause: "x" })).toBe("");
    expect(evidenceSummary(null)).toBe("");
  });

  it("10. matchesVerdictLevel sin filtro devuelve todo", () => {
    expect(matchesVerdictLevel(null, "")).toBe(true);
    expect(matchesVerdictLevel(null, null)).toBe(true);
    expect(matchesVerdictLevel({ level: "exito", cause: "x" }, undefined)).toBe(true);
  });

  it("11. matchesVerdictLevel filtra por nivel", () => {
    const v: RunVerdictPayload = { level: "advertencia", cause: "falso_rojo_probable" };
    expect(matchesVerdictLevel(v, "advertencia")).toBe(true);
    expect(matchesVerdictLevel(v, "error_real")).toBe(false);
  });

  it("12. matchesVerdictLevel sin veredicto no matchea un filtro explicito", () => {
    expect(matchesVerdictLevel(null, "exito")).toBe(false);
    expect(matchesVerdictLevel(undefined, "advertencia")).toBe(false);
  });
});

describe("plan 269 F4 — la fila del historial", () => {
  it("13. verdictChipTone cubre los 4 tonos", () => {
    expect(verdictChipTone("exito")).toBe("success");
    expect(verdictChipTone("error")).toBe("danger");
    expect(verdictChipTone("espera")).toBe("neutral");
    expect(verdictChipTone("atencion")).toBe("warning");
  });

  it("14. filtrar una lista por nivel", () => {
    const rows = [
      { id: 1, run_verdict: { level: "exito", cause: "cierre_limpio_con_entrega" } },
      { id: 2, run_verdict: { level: "advertencia", cause: "falso_rojo_probable" } },
      { id: 3, run_verdict: { level: "error_real", cause: "error_sin_entrega_suficiente" } },
      { id: 4, run_verdict: { level: "advertencia", cause: "espera_cuota" } },
    ];
    const soloAdv = rows.filter((r) => matchesVerdictLevel(r.run_verdict, "advertencia"));
    expect(soloAdv.map((r) => r.id)).toEqual([2, 4]);
    const todos = rows.filter((r) => matchesVerdictLevel(r.run_verdict, ""));
    expect(todos).toHaveLength(4);
  });
});

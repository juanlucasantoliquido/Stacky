import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { GatewayError, userFacingMessage } from "../api/gatewayError";

/**
 * Plan 273 F4.6 (cierra C1) — el error legible LLEGA A LA PANTALLA en las 10
 * superficies cuyo backend reescribe F5.
 *
 * Sin esta fase, F5 solo REUBICA el nombre de la flag de `error` a `detail.flag`
 * dentro del mismo string crudo que client.ts aplana, y los smokes 5 y 6 fallan
 * con el plan entero aplicado.
 */

const SRC = resolve(__dirname, "..");
const read = (rel: string) => readFileSync(resolve(SRC, rel), "utf8");

/** Las 10 superficies gateadas. 12 ocurrencias medidas el 2026-07-30. */
const GATED_SURFACES = [
  "components/dbcompare/CompareWizard.tsx",
  "components/dbcompare/DataParitySection.tsx",
  "components/dbcompare/SqlViewer.tsx",
  "components/dbcompare/DemoSandboxPanel.tsx",
  "components/dbcompare/ScriptsPanel.tsx",
  "components/dbcompare/useCompareRun.ts",
  "evolution/FitnessSection.tsx",
  "evolution/KnowledgeSection.tsx",
  "evolution/PlansSection.tsx",
  "pages/EvolutionCenterPage.tsx",
];

/**
 * LAS DOS FORMAS del modismo (v3, C26). Prohibir solo `: String(` dejaba pasar
 * `: "literal"`, que aplana IDENTICO (pinta el mismo err.message).
 * Multilinea a proposito: en CompareWizard el modismo estaba partido en 3 lineas.
 */
const RAW_IDIOM =
  /[A-Za-z_$]+\s+instanceof\s+Error\s*\n?\s*\?\s*[A-Za-z_$]+\.message\s*\n?\s*:\s*(String\(|["'])/g;

describe("plan273 F4.6 — las 10 superficies gateadas muestran la frase, no el aplanado", () => {
  it("las_10_superficies_gateadas_usan_userFacingMessage", () => {
    const missing = GATED_SURFACES.filter((f) => !read(f).includes("userFacingMessage("));
    expect(
      missing,
      `estas superficies siguen sin usar userFacingMessage():\n${missing.join("\n")}`
    ).toEqual([]);
  });

  it("las_10_superficies_gateadas_no_aplanan", () => {
    // ESTE ES EL GATE CONTRA EL DEFECTO.
    const hits: string[] = [];
    for (const f of GATED_SURFACES) {
      const src = read(f);
      const lines = src.split("\n");
      for (const m of src.matchAll(RAW_IDIOM)) {
        const line = src.slice(0, m.index).split("\n").length;
        hits.push(`${f}:${line}: ${lines[line - 1]?.trim() ?? ""}`);
      }
    }
    expect(
      hits,
      `${hits.length} ocurrencia(s) del modismo que aplana siguen vivas en las ` +
        `superficies gateadas:\n${hits.join("\n")}`
    ).toEqual([]);
  });

  it("el_banner_del_comparador_no_puede_mostrar_STACKY", () => {
    // El cuerpo REAL que el backend devuelve tras F5.
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      JSON.stringify({
        ok: false,
        error: "feature_disabled",
        message: "El Comparador de BD está desactivado.",
        detail: { flag: "STACKY_DB_COMPARE_ENABLED" },
      })
    );
    const r = userFacingMessage(e);
    expect(r.title).toBe("El Comparador de BD está desactivado.");
    expect(r.title).not.toMatch(/STACKY_[A-Z_]+/);
    expect(r.title).not.toMatch(/^\d{3}/);
    expect(r.title).not.toContain("feature_disabled");
    expect(r.flag).toBe("STACKY_DB_COMPARE_ENABLED");
  });

  it("la_rama_del_409_del_comparador_sobrevive", () => {
    // Tripwire: migrar no puede romper uno de los 7 parsers de F4.5.
    const src = read("components/dbcompare/CompareWizard.tsx");
    expect(src.includes("isBusyError"), "se perdio isBusyError").toBe(true);
    expect(
      src.includes('message.startsWith("409")'),
      "se perdio el parser del 409 (es una fila de LEGACY_PARSERS en F4.5)"
    ).toBe(true);
  });
});

import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Plan 273 F4.5 — el formato de GatewayError.message es un CONTRATO con 7
 * consumidores. Este test los enumera. Si migras uno a userFacingMessage(),
 * BORRA su fila aca en el MISMO commit y bajá el conteo: es un ratchet que solo
 * baja. Si el conteo sube, alguien agrego un parser nuevo de string crudo en vez
 * de usar el contrato estructurado.
 */

const SRC = resolve(__dirname, "..");
const read = (rel: string) => readFileSync(resolve(SRC, rel), "utf8");

const LEGACY_PARSERS: Array<[string, string]> = [
  ["components/dbcompare/CompareWizard.tsx", 'message.startsWith("409")'],
  ["components/devops/ProductionFlow.tsx", "message.indexOf(': ')"],
  ["components/devops/SectionDoctorButton.tsx", "message.indexOf(': ')"],
  ["components/devops/VariablesSection.tsx", "message.indexOf(': ')"],
  ["components/devops/VariablesSection.tsx", "message.includes('variables_unavailable')"],
  ["components/ExecutionErrorAnalysisBlock.tsx", "message.match(/^(\\d{3})\\s/)"],
  ["components/AgentLaunchModal.tsx", 'String(e).includes("503")'],
];

describe("plan273 F4.5 — los 7 parsers legacy del string aplanado", () => {
  it("los_7_parsers_siguen_presentes_o_el_conteo_bajo", () => {
    const found: string[] = [];
    const missing: string[] = [];
    for (const [file, fragment] of LEGACY_PARSERS) {
      const p = resolve(SRC, file);
      if (!existsSync(p)) {
        missing.push(`${file} (no existe)`);
        continue;
      }
      if (read(file).includes(fragment)) found.push(`${file} :: ${fragment}`);
      else missing.push(`${file} :: ${fragment}`);
    }
    // RATCHET: solo baja. Si alguien MIGRA un parser, baja el conteo y hay que
    // borrar su fila de LEGACY_PARSERS en el MISMO commit.
    expect(
      found.length,
      `el conteo de parsers legacy SUBIO a ${found.length}: alguien agrego un parser ` +
        `nuevo del string crudo en vez de usar el contrato estructurado.`
    ).toBeLessThanOrEqual(7);
    // Y no puede estar vacio por un regex/fragmento mal escrito: eso pasaria EN
    // FALSO. Si migras de verdad, bajá tanto la lista como este umbral.
    expect(
      found.length,
      `el censo encontro solo ${found.length} de 7 parsers. Filas que no matchean:\n` +
        missing.join("\n") +
        `\nSi migraste uno a userFacingMessage(), borrá su fila. Si NO lo migraste, ` +
        `el fragmento esta mal escrito y el ratchet estaria contando en falso.`
    ).toBe(7);
  });

  it("el_formato_del_message_esta_congelado", () => {
    const src = read("api/gatewayError.ts");
    expect(
      src.includes("`${status} ${statusText}: ${rawText}`"),
      "gatewayError.ts ya no construye el message con la plantilla historica exacta: " +
        "los 7 parsers de arriba dejan de matchear EN SILENCIO"
    ).toBe(true);
  });

  it("request_lanza_GatewayError_no_Error_plano", () => {
    const src = read("api/client.ts");
    expect(src.includes("throw new GatewayError("), "client.ts no lanza GatewayError").toBe(true);
    expect(
      src.includes("throw new Error(`${res.status} "),
      "client.ts todavia lanza el Error plano aplanado"
    ).toBe(false);
  });
});

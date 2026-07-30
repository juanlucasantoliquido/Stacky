import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, join } from "node:path";

/**
 * Plan 273 F4.7 — RATCHET. El modismo `X instanceof Error ? X.message : <fallback>`
 * pinta al operador el string aplanado de client.ts (`403 FORBIDDEN: {...}`).
 *
 * LAS DOS FORMAS CUENTAN (v3, C26). El v2 exigia el fallback `String(` y con eso
 * veia 40 de 127: la forma `: "texto literal"` aplana IDENTICO (pinta el mismo
 * X.message) y es la MAYORITARIA — 87 ocurrencias ya en el arbol. Un ratchet que
 * solo mira `String(` se queda verde mientras la superficie crece por la otra
 * forma, que es precisamente como esta clase de deuda volvio otras veces.
 *
 * Medido el 2026-07-30: 127 ocurrencias en 61 archivos (40 con `String(` + 87 con
 * literal). F4.6 migra 12 (las 10 superficies con gate de flag) => techo 115.
 * ESTE NUMERO SOLO BAJA. Si migras mas sitios a userFacingMessage(), BAJA el techo
 * en el MISMO commit. Si sube, alguien agrego un aplanado nuevo en vez de usar
 * userFacingMessage(): no subas el techo, migra el sitio.
 */
const MAX_RAW_ERROR_SITES = 115;

const RAW_IDIOM =
  /[A-Za-z_$]+\s+instanceof\s+Error\s*\n?\s*\?\s*[A-Za-z_$]+\.message\s*\n?\s*:\s*(String\(|["'])/g;
/** Las dos mitades, solo para `el_censo_cubre_las_dos_variantes`. */
const RAW_STRING_FORM =
  /[A-Za-z_$]+\s+instanceof\s+Error\s*\n?\s*\?\s*[A-Za-z_$]+\.message\s*\n?\s*:\s*String\(/g;
const RAW_LITERAL_FORM =
  /[A-Za-z_$]+\s+instanceof\s+Error\s*\n?\s*\?\s*[A-Za-z_$]+\.message\s*\n?\s*:\s*["']/g;

const SRC = resolve(__dirname, "..");

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

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

/** Todos los .ts/.tsx de produccion (sin tests). */
function productionFiles(): string[] {
  return walk(SRC).filter((p) => {
    const rel = p.slice(SRC.length + 1).replace(/\\/g, "/");
    return !rel.includes("__tests__") && !/\.test\./.test(rel);
  });
}

function census(re: RegExp): { total: number; sites: string[]; files: number } {
  const sites: string[] = [];
  let files = 0;
  for (const p of productionFiles()) {
    const src = readFileSync(p, "utf8");
    const rel = p.slice(SRC.length + 1).replace(/\\/g, "/");
    let n = 0;
    for (const m of src.matchAll(new RegExp(re.source, "g"))) {
      const line = src.slice(0, m.index).split("\n").length;
      sites.push(`${rel}:${line}`);
      n++;
    }
    if (n) files++;
  }
  return { total: sites.length, sites, files };
}

describe("plan273 F4.7 — ratchet de superficie de error cruda", () => {
  it("el_censo_no_es_vacio", () => {
    // Un regex que deja de matchear daria 0 y los otros casos pasarian EN FALSO.
    // Mismo modo de falla que tapa test_las_dos_listas_son_no_vacias del plan 259.
    const { total } = census(RAW_IDIOM);
    expect(total, `el censo encontro ${total} ocurrencias: el regex esta roto`).toBeGreaterThanOrEqual(100);
  });

  it("el_censo_cubre_las_dos_variantes", () => {
    // v3, C26: sin este caso, un RAW_IDIOM que por un parentesis mal puesto
    // colapsara a una sola forma volveria a congelar el 26% de la superficie y
    // NADA lo diria.
    const s = census(RAW_STRING_FORM).total;
    const l = census(RAW_LITERAL_FORM).total;
    expect(s, `forma con String(: ${s}`).toBeGreaterThanOrEqual(20);
    expect(l, `forma con literal: ${l}`).toBeGreaterThanOrEqual(60);
  });

  it("la_superficie_cruda_no_crece", () => {
    const { total, sites } = census(RAW_IDIOM);
    expect(
      total <= MAX_RAW_ERROR_SITES,
      `la superficie de error cruda SUBIO a ${total} (techo ${MAX_RAW_ERROR_SITES}). ` +
        `Migra el sitio nuevo a userFacingMessage() en vez de subir el techo.\n` +
        sites.join("\n")
    ).toBe(true);
  });

  it("las_10_superficies_gateadas_no_estan_en_el_censo", () => {
    const { sites } = census(RAW_IDIOM);
    const leaked = sites.filter((s) => GATED_SURFACES.some((g) => s.startsWith(`${g}:`)));
    expect(
      leaked,
      `F4.6 dejo sin migrar estas ocurrencias en superficies gateadas:\n${leaked.join("\n")}`
    ).toEqual([]);
  });

  it("el_barrido_recorre_todo_src", () => {
    // Gate anti-glob-roto: un barrido que no matchea nada daria 0 archivos y 0
    // ocurrencias, y todo pasaria en falso. Medido el 2026-07-30: 785 archivos.
    const n = productionFiles().length;
    expect(n, `el barrido escaneo ${n} archivos: el recorrido esta roto`).toBeGreaterThan(300);
  });
});

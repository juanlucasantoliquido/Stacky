/**
 * dbcompareSummaryShapeRatchet.test.ts — Plan 266 F4.
 *
 * Ningún archivo de components/dbcompare/ puede leer by_severity / by_action /
 * by_object_type sin pasar por summaryShape.ts. Es un RATCHET, no una foto: caza
 * al archivo nuevo (o al viejo que retrocede), no solo el estado de hoy.
 *
 * DOS reglas, no una (R1 sola no ve `r.summary!.by_severity;` porque después del
 * identificador viene `;`; R2 sola no ve `cell.by_severity.danger` porque no hay
 * `.summary` en la línea — ver §F4.2 del plan).
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const DB_COMPARE_DIR = path.resolve(__dirname, "../components/dbcompare");
const ALLOWLIST: string[] = []; // vacía a propósito: el único legítimo (summaryShape.ts) usa corchetes+string, no matchea.

// R1 — acceso profundo: el mapa leído como objeto, con punto o con corchete.
const R1 = /by_(severity|action|object_type)\s*[.[]/;

// R2 — lectura directa del contenedor: el mapa sacado de `.summary` (con o sin `!`).
const R2 = /\.summary\s*!?\s*\.by_(severity|action|object_type)/;

// EXENCIÓN (misma línea): la lectura pasa por el normalizador.
const EXENTO = ["safeSummary(", "safeBySeverity(", "safeByAction(", "safeByObjectType("];

interface Violacion {
  file: string;
  line: number;
  text: string;
}

/** Recorre recursivamente un directorio y devuelve rutas absolutas de archivos. */
function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

/** Archivos .ts/.tsx de dbcompare/, excluidos los *.test.tsx? y __tests__/. */
function archivos(): string[] {
  return walk(DB_COMPARE_DIR)
    .filter((f) => /\.tsx?$/.test(f))
    .filter((f) => !/\.test\.tsx?$/.test(f))
    .filter((f) => !f.split(path.sep).includes("__tests__"))
    .filter((f) => !ALLOWLIST.includes(path.relative(DB_COMPARE_DIR, f)));
}

/** Líneas violatorias de un bloque de código fuente (exportado para testear con fixtures). */
export function violaciones(source: string, file = "<fixture>"): Violacion[] {
  const out: Violacion[] = [];
  source.split(/\r?\n/).forEach((line, i) => {
    const matches = R1.test(line) || R2.test(line);
    if (!matches) return;
    const exento = EXENTO.some((marca) => line.includes(marca));
    if (!exento) out.push({ file, line: i + 1, text: line.trim() });
  });
  return out;
}

function censo(): Violacion[] {
  const out: Violacion[] = [];
  for (const full of archivos()) {
    const src = fs.readFileSync(full, "utf-8");
    out.push(...violaciones(src, path.relative(DB_COMPARE_DIR, full)));
  }
  return out;
}

// Censado 2026-07-29: 57 archivos .ts/.tsx no-test en components/dbcompare/.
// El margen (45) tolera borrados legítimos de archivos sueltos, NO un refactor
// que mueva la carpeta y deje el censo vacío (que es lo que este test caza).
const FIXTURE_HISTORICO = [
  "const sev = r.summary!.by_severity;", // radarLogic.ts:60 (forma histórica, ya arreglada)
  "{run.summary.by_severity.danger}", // RunsTimeline.tsx:37
  "{run.summary.by_severity.warn} {run.summary.by_severity.info}", // RunsTimeline.tsx:38
  "const sev = r.diff.summary.by_severity;", // EnvironmentRadar.tsx:144
  "{(cell.by_severity.danger || 0) + (cell.by_severity.warn || 0)}", // EnvironmentRadar.tsx:215
  ".map((t) => `${summary.by_object_type[t]} ${OBJECT_TYPE_LABEL[t]}`)", // SummaryHero.tsx:145
  "return SEVERITY_ORDER.map((s) => ({ s, count: diff.summary.by_severity[s] }));", // svgMath.ts:43
  "return ACTION_ORDER.map((a) => ({ a, count: diff.summary.by_action[a] }));", // svgMath.ts:47
].join("\n");

describe("Plan 266 F4 — centinela: cero accesos profundos al summary sin guarda", () => {
  it("no hay accesos profundos sin guarda en dbcompare/", () => {
    const malos = censo();
    expect(malos, JSON.stringify(malos)).toEqual([]);
  });

  it("el detector encuentra las 8 formas históricas", () => {
    expect(violaciones(FIXTURE_HISTORICO)).toHaveLength(8);
  });

  it("R2 caza el non-null assertion", () => {
    expect(violaciones("const sev = r.summary!.by_severity;")).toHaveLength(1);
  });

  it("R1 caza el acceso con punto", () => {
    expect(violaciones("{cell.by_severity.danger}")).toHaveLength(1);
  });

  it("R1 caza el acceso computado", () => {
    expect(violaciones("summary.by_object_type[t]")).toHaveLength(1);
  });

  it("la forma normalizada NO es violación", () => {
    expect(violaciones("const sev = safeSummary(run.summary).by_severity;")).toHaveLength(0);
  });

  it("la declaración de tipo NO es violación", () => {
    expect(violaciones("  by_severity: Record<Severity, number>;")).toHaveLength(0);
  });

  it("el literal de objeto NO es violación", () => {
    expect(violaciones("by_severity: { info: 0, warn: 0, danger: 0 },")).toHaveLength(0);
  });

  it("la lectura por corchete con literal de string NO es violación", () => {
    expect(violaciones('const src = raw["by_severity"];')).toHaveLength(0);
  });

  it("el guard con || NO es violación", () => {
    expect(violaciones("const sev = cell.by_severity || EMPTY_BY_SEVERITY;")).toHaveLength(0);
  });

  it("la ALLOWLIST está vacía", () => {
    expect(ALLOWLIST).toEqual([]);
  });

  it("el censo mira al menos 45 archivos", () => {
    expect(archivos().length).toBeGreaterThanOrEqual(45);
  });
});

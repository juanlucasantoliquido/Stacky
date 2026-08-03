// Plan 282 F0 — censo PARTICIONADO de rotulos ADO en el frontend (K2).
//
// Dos defectos medidos del censo v1 de este plan: (1) el total real es 118, no
// 96; (2) su regex exigia comilla o `>` en la misma linea, asi que NO veia
// `App.tsx` — el ofensor #1 del ranking — ni `TicketBoard.tsx`, porque ahi el
// rotulo es TEXTO JSX SUELTO. Un censo que no ve al ofensor principal no puede
// ser el gate de la fase que lo arregla.
//
// Por que particion y no techo: los archivos que F4 alcanza suman una fraccion
// del total. El resto son superficies que DEBEN decir ADO (selector de tracker,
// migrador ADO->GitLab, preview de pipeline de Azure) o pantallas ADO-only por
// diseño. Un techo global mezcla las dos cosas y obliga a elegir entre incumplir
// el gate o hacer trabajo fuera de alcance.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const SRC = join(__dirname, "..", "..");   // desde src/services/__tests__/ -> src/

/** ALLOWLIST — superficies donde decir "ADO" es CORRECTO. Cada entrada lleva su
 *  motivo escrito: esta lista es la puerta trasera del gate y no se toca sin
 *  justificar en el PR. Rutas relativas a src/, con separador POSIX. */
const LEGITIMOS: Record<string, string> = {
  // Seleccion/configuracion de tracker: el operador elige ENTRE trackers.
  "components/NewProjectModal.tsx":        "selector de tracker en el alta de proyecto",
  "components/EditProjectModal.tsx":       "selector de tracker en la config del proyecto",
  "pages/SettingsPage.tsx":                "config global del tracker",
  // Migrador ADO->GitLab: ADO es literalmente el origen.
  "pages/MigratorPage.tsx":                "migrador ADO->GitLab: ADO es el origen",
  "components/MigratorWizard.tsx":         "idem migrador",
  "components/MigratorMappingTable.tsx":   "idem migrador",
  // Pipelines: el preview YAML de Azure Pipelines es un artefacto ADO.
  "components/devops/PipelineYamlPreview.tsx":    "YAML de Azure Pipelines",
  "components/devops/PipelineBuilderSection.tsx": "builder de Azure Pipelines",
  "components/devops/BlockProperties.tsx":        "bloques de Azure Pipelines",
  "components/devops/CommitPipelineModal.tsx":    "commit de azure-pipelines.yml",
  "components/devops/OneClickPublishModal.tsx":   "publicacion de pipeline ADO",
  "components/devops/PipelineEnvMatrixPanel.tsx": "matriz de entornos ADO",
  "components/devops/ProductionFlow.tsx":         "flujo de release ADO",
  "components/devops/PublicationsSection.tsx":    "publicaciones ADO",
  "components/devops/TriggerPipelineSection.tsx": "trigger de pipeline ADO",
  "components/devops/VariablesSection.tsx":       "variables de pipeline ADO",
  "pages/DevOpsPage.tsx":                         "cockpit DevOps ADO",
  "components/PipelineGeneratorPanel.tsx":        "generador de azure-pipelines.yml",
  "hooks/useAutoFillBlocks.ts":                   "autofill de bloques ADO",
  // Pantallas ADO-only por diseño (F7 las gatea, no las traduce).
  "pages/PMCommandCenter.tsx":  "PM Suite v1 es ADO-only (api/pm.py)",
  "pages/SprintBoardPage.tsx":  "Sprint Board es ADO-only (api/pm.py)",
  "pages/UserStatsPage.tsx":    "User Stats es ADO-only (api/pm.py)",
  // El diccionario de rotulos: "ADO" es su DATO, no su bug.
  "lib/trackerLabels.ts":       "el mapa NOMBRES contiene la cadena por definicion",

  // ── Agregadas AL IMPLEMENTAR el plan 282, cada una con su motivo. El baseline
  //    medido fue 100 rotulos ruteables en 34 archivos, no los 40 que el plan
  //    predecia: la allowlist de 23 se calibro contra un universo equivocado. ──
  "lib/tabsPorTracker.ts":
    "el motivo del tooltip DICE 'requiere Azure DevOps': nombrar el tracker que falta ES la funcion del mensaje",
  "components/shell/shellNav.ts":
    "TAB_META es el label ESTATICO de fallback; el ruteo lo hace labelDeTab en el render (A3) y 4 suites congelan este objeto",
  "components/StructuredOutput.tsx":
    "CITATION_RE detecta la cadena 'ADO-XXXX' EN EL TEXTO del agente: es su dato de entrada, no un rotulo de UI",
  "components/devops/PipelineLintPanel.tsx":
    "lint de azure-pipelines.yml: mismo criterio que el resto de components/devops",
  "components/EpicFromBriefModal.tsx":
    "DEUDA DECLARADA: archivo con cambios sin commitear de OTRA sesion (fix de la epica duplicada). Se rutea en el barrido siguiente, no en este plan",

  // ── Agregadas 2026-08-02 al consolidar las ramas docs/plan-27x en main. Las
  //    tres nombran el tracker CONDICIONADAS al proveedor real, que es justo el
  //    patron que este plan buscaba instalar; el detector cuenta lineas y no
  //    puede distinguirlo de un rotulo fijo. NO se rutean por trackerLabels.ts a
  //    proposito: `nombreLargoDeTracker()` pasa por `clave()`, y con el
  //    kill-switch STACKY_TRACKER_LABELS_GLOBAL_ENABLED en OFF devuelve siempre
  //    "azure_devops" (trackerLabels.ts:55), o sea que una pipeline de GitLab
  //    quedaria rotulada al reves — peor que el rotulo que se quiere evitar. ──
  "components/devops/pipelineCopilotModel.ts":
    "el mensaje SIN_DESTINO nombra los DOS trackers a proposito ('no puede saber si la pipeline va a Azure DevOps o a GitLab') para decirle al operador que le falta configurar; no rotula un destino",
  "components/devops/PipelineCopilotSection.tsx":
    "condicional por proveedor (target.provider === 'ado' ? ... : 'GitLab'): dice el nombre de Azure SOLO cuando el destino ES Azure, y GitLab cuando es GitLab",
  "incidents/incidentDevPrModel.ts":
    "NOMBRES_PROVEEDOR es un mapa de lookup: la clave azure_devops se traduce a su propio nombre presentable, igual que gitlab. Es un dato del diccionario, no un rotulo incondicional",
};

/** Archivos que este plan SI rutea. La allowlist no puede tragarselos: es el
 *  gate de que la puerta trasera no se use para el trabajo en alcance. */
const NUNCA_ALLOWLISTEABLES = [
  "App.tsx",
  "pages/TicketBoard.tsx",
  "pages/UnblockerPage.tsx",
  "components/FinishWorkButton.tsx",
  "components/commandPaletteData.ts",
  "services/entityActions.ts",
  "services/copyFormats.ts",
  "utils/trackerUrls.ts",
];

function archivosFuente(dir: string): string[] {
  const salida: string[] = [];
  for (const entrada of readdirSync(dir)) {
    if (entrada === "node_modules" || entrada === "__tests__") continue;
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) salida.push(...archivosFuente(ruta));
    else if (/\.(tsx?|jsx)$/.test(entrada) && !/\.test\.tsx?$/.test(entrada)) salida.push(ruta);
  }
  return salida;
}

/** Cuenta rotulos ADO VISIBLES.
 *
 *  Dos exigencias opuestas, y las dos se verifican con guardas:
 *  1. Tiene que VER el texto JSX suelto (`📋 Tickets ADO` sin comillas ni `>`
 *     en la misma linea). Era el defecto del censo v1: no veia al ofensor #1.
 *  2. NO tiene que contar comentarios. El codigo esta en español, asi que
 *     contarlos da falsos positivos; y los comentarios JSX (`{​/* ... *​/}`) y los
 *     bloques multilinea NO los ve un filtro de "empieza con //": la linea de
 *     continuacion de un bloque arranca con texto suelto.
 *  Por eso se STRIPEAN los comentarios (preservando saltos de linea, para no
 *  alterar el conteo por lineas) y recien despues se busca. */
export function rotulosAdo(texto: string): number {
  // Maquina de estados POR LINEA. Un stripper de `/* ... */` sobre el texto
  // entero se deja engañar por un `/*` dentro de un string o de un regex
  // literal (hay varios en este repo): blanquea el `//` de lineas siguientes y
  // convierte comentarios en falsos rotulos. Mirando solo el ARRANQUE de cada
  // linea eso es imposible.
  let dentroDeBloque = false;
  let total = 0;
  for (const linea of texto.split("\n")) {
    const t = linea.trim();
    if (dentroDeBloque) {
      if (t.includes("*/")) dentroDeBloque = false;
      continue;                                   // la linea entera es comentario
    }
    if (/^(\/\/|\*|\{?\/\*)/.test(t)) {           // //, continuacion `*`, /* y {/*
      if (/^\{?\/\*/.test(t) && !t.includes("*/")) dentroDeBloque = true;
      continue;
    }
    if (/\b(ADO|Azure DevOps)\b/.test(linea)) total++;
  }
  return total;
}

function rel(f: string): string { return relative(SRC, f).split(sep).join("/"); }

function censoRuteable(): Record<string, number> {
  const ruteables: Record<string, number> = {};
  for (const f of archivosFuente(SRC)) {
    const r = rel(f);
    if (r in LEGITIMOS) continue;
    const n = rotulosAdo(readFileSync(f, "utf-8"));
    if (n > 0) ruteables[r] = n;
  }
  return ruteables;
}

describe("Plan 282 F0 — censo particionado de rotulos ADO (K2)", () => {
  it("guarda anti-falso-verde: el detector detecta y descarta comentarios", () => {
    // (a) LO QUE TIENE QUE VER — si alguno da 0, el censo esta ciego.
    expect(rotulosAdo(`const x = "Tickets ADO";`)).toBe(1);
    expect(rotulosAdo(`              📋 Tickets ADO`)).toBe(1);   // texto JSX suelto (el bug de v1)
    expect(rotulosAdo(`  title="Abrir en Azure DevOps"`)).toBe(1);
    expect(rotulosAdo(`  <span>ADO-{t.ado_id}</span>`)).toBe(1);

    // (b) LO QUE NO TIENE QUE VER — comentarios: no son rotulos.
    expect(rotulosAdo(`// comentario sobre ADO`)).toBe(0);
    expect(rotulosAdo(`{/* Ledger de publicaciones ADO */}`)).toBe(0);
    expect(rotulosAdo("/* Paridad del tracker (ADO)\n   y su ADO de abajo */")).toBe(0);
    expect(rotulosAdo(`const x = "GitLab";`)).toBe(0);
  });

  it("guarda: el censo VE un ofensor CONOCIDO del arbol", () => {
    // Un censo que solo sabe detectar en cadenas sinteticas no prueba nada sobre
    // el repo. `pages/PMCommandCenter.tsx` esta en la allowlist justamente
    // porque SI tiene rotulos ADO: si esto da 0, el regex volvio a estar mal.
    const conocido = readFileSync(join(SRC, "pages", "PMCommandCenter.tsx"), "utf-8");
    expect(rotulosAdo(conocido)).toBeGreaterThan(0);
  });

  it("K2: CERO rotulos ADO en el conjunto RUTEABLE", () => {
    expect(censoRuteable()).toEqual({});
  });

  it("sentinela: la allowlist no crece sin justificacion", () => {
    // 23 en el plan + 5 agregadas al implementarlo + 3 agregadas el 2026-08-02
    // al consolidar las ramas docs/plan-27x, con motivo escrito una por una (ver
    // el bloque de arriba). Subir este numero exige justificar la entrada nueva
    // en el PR.
    expect(Object.keys(LEGITIMOS).length).toBe(31);
    // Toda entrada debe traer motivo NO vacio: sin esto la allowlist es un agujero.
    for (const [k, v] of Object.entries(LEGITIMOS)) expect(v.trim().length, k).toBeGreaterThan(0);
  });

  it("sentinela: la allowlist NO puede tragarse un archivo en alcance", () => {
    // Sin esto, la forma barata de poner el censo en verde seria allowlistear
    // justo los archivos que la fase tenia que arreglar.
    for (const ruta of NUNCA_ALLOWLISTEABLES) {
      expect(ruta in LEGITIMOS, `${ruta} esta en la allowlist: es trabajo en alcance`).toBe(false);
    }
  });
});

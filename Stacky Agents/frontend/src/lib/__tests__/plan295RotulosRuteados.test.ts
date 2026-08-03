// Plan 295 F11 — los rotulos de las dos pantallas LIMPIAS dejan de hablar en
// vocabulario de Azure DevOps cuando el proyecto activo es GitLab.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { nombreDeNivel } from "../trackerLabels";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const leer = (p: string) => readFileSync(resolve(SRC, p), "utf-8");

// Los literales se arman por concatenacion A PROPOSITO: si estuvieran escritos
// enteros en este archivo no pasaria nada (el censo mira otros archivos), pero es
// el mismo cuidado que hay que tener en los archivos censados, donde un comentario
// que NOMBRA el patron rompe el gate por grep.
const L_FEATURE = "[" + "Feature]";
const L_TASK = "[" + "Task]";
const L_FEATURES = "Feature" + "(s)";
const L_ESTADOS_ADO = "Ej: Done," + " Closed, Resolved";

describe("plan 295 F11 — rotulos ruteados por tracker", () => {
  it("1. en GitLab el nivel intermedio NO se llama Feature", () => {
    const n = nombreDeNivel("gitlab", "intermedio");
    expect(n).not.toBe("Feature");
    expect(n.trim().length).toBeGreaterThan(0);
  });

  it("2. NO-REGRESION: en Azure DevOps sigue siendo Feature", () => {
    expect(nombreDeNivel("azure_devops", "intermedio")).toBe("Feature");
  });

  it("3. sin tracker conocido cae al vocabulario de hoy (Task)", () => {
    expect(nombreDeNivel(null, "hoja")).toBe("Task");
    expect(nombreDeNivel(undefined, "hoja")).toBe("Task");
  });

  it("4. censo: EpicChildrenPanel ya no trae los rotulos de Azure DevOps", () => {
    const t = leer("components/EpicChildrenPanel.tsx");
    expect(t).not.toContain(L_FEATURE);
    expect(t).not.toContain(L_TASK);
    expect(t).not.toContain(L_FEATURES);
  });

  it("5. censo: FinishWorkButton ya no trae el placeholder de Azure DevOps", () => {
    expect(leer("components/FinishWorkButton.tsx")).not.toContain(L_ESTADOS_ADO);
  });

  it("6. EpicChildrenPanel usa la variable REAL del componente", () => {
    // Los casos 4 y 5 son de AUSENCIA: pasarian en falso si la ruta estuviera mal.
    // Este es de PRESENCIA y ancla la ruta. Ademas caza el error concreto del v1
    // del plan, que escribia `trackerActivo` -- una variable que NO existe en el
    // archivo (la real es `trackerType`, :45) y que habria dado TS2304 recien en
    // el `tsc --noEmit` de F12, o sea al final.
    const t = leer("components/EpicChildrenPanel.tsx");
    expect(t).toContain("nombreDeNivel(trackerType");
    expect(t).not.toContain("trackerActivo");
  });
});

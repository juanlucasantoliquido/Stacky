// Plan 295 F1 — gate de que el dead code medido de gitlabProfileModel NO vuelva.
// Se prueba con lectura de disco (no con import) porque el punto ES la ausencia
// del archivo: un import fallaria en compilacion y no en el assert.
import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));
const DEVOPS = resolve(AQUI, "..");

describe("plan 295 F1 — gitlabProfileModel es dead code borrado", () => {
  it("el modulo NO existe", () => {
    expect(existsSync(resolve(DEVOPS, "gitlabProfileModel.ts"))).toBe(false);
  });

  it("su test tampoco existe (se borro junto con el modulo)", () => {
    expect(existsSync(resolve(DEVOPS, "gitlabProfileModel.test.ts"))).toBe(false);
  });

  // ASSERT DE PRESENCIA, no de ausencia (G7): comprueba que el archivo que SI
  // debe existir sigue existiendo. Sin este, un typo en DEVOPS haria pasar los
  // dos asserts de arriba EN FALSO (todo "no existe" en una ruta equivocada).
  it("el panel que se creia consumidor sigue en su lugar", () => {
    expect(existsSync(resolve(DEVOPS, "PipelineLintPanel.tsx"))).toBe(true);
  });
});

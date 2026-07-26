/**
 * Plan 243 F1 — espejo TypeScript de TaskStep/DeploymentJob + fromParsedSpec como
 * NORMALIZADOR real (C21).
 *
 * Comando (§7.1 del plan):
 *   npx vitest run src/devops/__tests__/specBuilderTaskStep.test.ts
 *
 * Por qué importa fromParsedSpec: antes era literalmente `return dict as PipelineSpecDraft`,
 * un cast no-op que no valida nada. F5 (plan 244) le va a entregar un dict construido en
 * el backend que va DIRECTO al estado de React del builder; si le falta
 * stages[].jobs[].steps, el panel rompe al renderizar y el operador ve una pantalla
 * muerta en vez de un error del generador.
 */
import { describe, expect, it } from "vitest";

import {
  emptySpec,
  fromParsedSpec,
  specsEqual,
  starterSpec,
  toSpecDict,
  type PipelineSpecDraft,
} from "../specBuilder";

describe("Plan 243 F1 — task steps en el draft", () => {
  it("toSpecDict hace round-trip de un draft con task steps y deployments", () => {
    const spec: PipelineSpecDraft = {
      name: "ci-online",
      stages: [
        {
          name: "Build",
          display_name: "Build & Test",
          pool_vm_image: "windows-2022",
          jobs: [
            {
              name: "BuildJob",
              display_name: "Restore -> Build",
              steps: [],
              task_steps: [
                { name: "NuGet", task: "NuGetToolInstaller@1", inputs: { versionSpec: "6.x" }, env: {} },
                { name: "MSBuild", task: "VSBuild@1", inputs: { solution: "$(solution)" }, condition: "succeeded()", env: {} },
              ],
              runner_tags: [],
              variables: {},
              artifacts: [],
              services: [],
            },
          ],
        },
        {
          name: "Deploy",
          pool_name: "TEST-Server",
          depends_on: ["Build"],
          jobs: [],
          deployments: [
            {
              name: "DeployWeb",
              environment: "Test",
              strategy: "runOnce",
              checkout: true,
              download_artifacts: ["AgendaWeb"],
              steps: [
                { name: "Deploy", task: "PowerShell@2", inputs: { filePath: "scripts/Deploy-Local.ps1" }, env: {} },
              ],
            },
          ],
        },
      ],
      variables: {},
      trigger_branches: ["main"],
      pr_disabled: true,
    };

    const dict = toSpecDict(spec) as any;
    expect(dict.stages[0].jobs[0].task_steps).toHaveLength(2);
    expect(dict.stages[0].jobs[0].task_steps[1].task).toBe("VSBuild@1");
    expect(dict.stages[1].deployments[0].environment).toBe("Test");
    expect(dict.stages[1].deployments[0].download_artifacts).toEqual(["AgendaWeb"]);
    expect(dict.pr_disabled).toBe(true);
    // Round-trip completo: normalizar lo serializado devuelve lo mismo.
    expect(toSpecDict(fromParsedSpec(dict))).toEqual(dict);
  });

  it("un draft del Plan 97 pasa idéntico por fromParsedSpec (retrocompatible)", () => {
    const viejo = starterSpec();
    const normalizado = fromParsedSpec(toSpecDict(viejo));
    expect(toSpecDict(normalizado)).toEqual(toSpecDict(viejo));
    expect(normalizado.stages[0].jobs[0].steps[0].script).toBe(
      'echo "reemplazar por el comando real"',
    );
  });

  it("un dict recortado sale COMPLETO en vez de romper el render", () => {
    // Lo peor que puede llegar del backend: stages sin jobs, jobs sin steps.
    const recortado = { name: "p", stages: [{ name: "Build", jobs: [{ name: "j" }] }] };
    const spec = fromParsedSpec(recortado);

    expect(Array.isArray(spec.stages)).toBe(true);
    expect(spec.variables).toEqual({});
    expect(spec.trigger_branches).toEqual([]);
    const job = spec.stages[0].jobs[0];
    // Estos cuatro arrays + variables son EXACTAMENTE los que el builder del Plan 97
    // mapea sin guarda: si alguno llega undefined, el panel muere al renderizar.
    expect(job.steps).toEqual([]);
    expect(job.runner_tags).toEqual([]);
    expect(job.artifacts).toEqual([]);
    expect(job.services).toEqual([]);
    expect(job.variables).toEqual({});
    // Los campos NUEVOS no se inyectan (ver test del badge), pero si vienen —aunque
    // vengan mal— salen como array utilizable.
    expect(fromParsedSpec({
      name: "p",
      stages: [{ name: "B", jobs: [{ name: "j", task_steps: "no soy array" }], deployments: null }],
    }).stages[0].jobs[0].task_steps).toEqual([]);
    expect(fromParsedSpec({
      name: "p",
      stages: [{ name: "B", jobs: [], deployments: "no soy array" }],
    }).stages[0].deployments).toEqual([]);
  });

  it("no inyecta campos nuevos en drafts viejos (no enciende el badge de cambios)", () => {
    // specsEqual() alimenta el badge "cambios sin guardar" (specBuilder.ts). Si el
    // normalizador agregara task_steps:[] a todo draft, un draft guardado con el
    // formato del Plan 97 dejaria de ser igual a si mismo al releerlo y el panel
    // mostraria cambios pendientes sin que el operador toque nada.
    const viejo = starterSpec();
    const releido = fromParsedSpec(toSpecDict(viejo));
    expect(specsEqual(viejo, releido)).toBe(true);
    expect(releido.stages[0].jobs[0].task_steps).toBeUndefined();
    expect(releido.stages[0].deployments).toBeUndefined();
  });

  it("descarta claves desconocidas en vez de arrastrarlas al estado", () => {
    const sucio = {
      name: "p",
      hackeame: "no deberia sobrevivir",
      stages: [
        {
          name: "Build",
          basura_de_stage: 1,
          jobs: [
            {
              name: "j",
              basura_de_job: true,
              steps: [{ name: "s", script: "echo", basura_de_step: [] }],
              task_steps: [{ name: "t", task: "VSBuild@1", inputs: { solution: "x" }, basura: 9 }],
            },
          ],
        },
      ],
    };
    const spec = fromParsedSpec(sucio) as any;
    expect(spec.hackeame).toBeUndefined();
    expect(spec.stages[0].basura_de_stage).toBeUndefined();
    expect(spec.stages[0].jobs[0].basura_de_job).toBeUndefined();
    expect(spec.stages[0].jobs[0].steps[0].basura_de_step).toBeUndefined();
    expect(spec.stages[0].jobs[0].task_steps[0].basura).toBeUndefined();
    // …pero lo bueno sobrevive
    expect(spec.stages[0].jobs[0].task_steps[0].inputs).toEqual({ solution: "x" });
    expect(spec.stages[0].jobs[0].steps[0].script).toBe("echo");
  });

  it("con null / basura devuelve emptySpec() en vez de romper", () => {
    expect(fromParsedSpec(null)).toEqual(emptySpec());
    expect(fromParsedSpec(undefined)).toEqual(emptySpec());
    expect(fromParsedSpec("no soy un spec")).toEqual(emptySpec());
    expect(fromParsedSpec(42)).toEqual(emptySpec());
    expect(fromParsedSpec({ stages: "tampoco soy un array" }).stages).toEqual([]);
  });
});

/**
 * Tests de specBuilder.ts - Plan 87 F3
 * TDD: lógica pura del editor de pipelines (sin React)
 */
import { describe, it, expect } from "vitest";
import {
  emptySpec,
  addStage,
  removeStage,
  moveStage,
  addJob,
  removeJob,
  moveJob,
  addStep,
  removeStep,
  moveStep,
  updateStage,
  updateJob,
  updateStep,
  toSpecDict,
  fromParsedSpec,
  mergeDraftsIntoProfile,
  starterSpec,
  validateSpecLocal,
  specsEqual,
  type PipelineSpecDraft,
} from "./specBuilder";

describe("specBuilder - F3 TDD", () => {
  describe("emptySpec", () => {
    it("emptySpec_shape", () => {
      const spec = emptySpec();
      expect(spec.name).toBe("");
      expect(spec.stages).toEqual([]);
      expect(spec.variables).toEqual({});
      expect(spec.trigger_branches).toEqual([]);
    });
  });

  describe("addStage - inmutabilidad y shape", () => {
    it("addStage_appends_and_is_immutable", () => {
      const original = emptySpec();
      const modified = addStage(original);

      // El original NO cambia
      expect(original).not.toBe(modified);
      expect(original.stages).toHaveLength(0);

      // El modificado tiene 1 stage con defaults
      expect(modified.stages).toHaveLength(1);
      expect(modified.stages[0].name).toBe("stage-1");
      expect(modified.stages[0].jobs).toEqual([]);
    });

    it("addStage_multiple_increment_name", () => {
      const spec1 = addStage(emptySpec());
      const spec2 = addStage(spec1);

      expect(spec2.stages).toHaveLength(2);
      expect(spec2.stages[0].name).toBe("stage-1");
      expect(spec2.stages[1].name).toBe("stage-2");
    });
  });

  describe("moveStage - mover sin mutar", () => {
    it("move_out_of_range_noop", () => {
      const spec = addStage(emptySpec());
      const originalSnapshot = JSON.parse(JSON.stringify(spec));

      // Mover hacia arriba con 1 solo stage (índice 0 → -1) = NOOP
      const result = moveStage(spec, 0, -1);

      // Igual al original
      expect(result).toEqual(spec);
      expect(JSON.stringify(result)).toBe(JSON.stringify(originalSnapshot));
    });

    it("moveStage_down_with_2_stages", () => {
      let spec = emptySpec();
      spec = addStage(spec); // stage-1
      spec = addStage(spec); // stage-2

      const moved = moveStage(spec, 0, 1); // Mover stage-1 hacia abajo

      expect(moved.stages[0].name).toBe("stage-2");
      expect(moved.stages[1].name).toBe("stage-1");
    });

    it("moveStage_up_with_2_stages", () => {
      let spec = emptySpec();
      spec = addStage(spec); // stage-1
      spec = addStage(spec); // stage-2

      const moved = moveStage(spec, 1, -1); // Mover stage-2 hacia arriba

      expect(moved.stages[0].name).toBe("stage-2");
      expect(moved.stages[1].name).toBe("stage-1");
    });
  });

  describe("removeStage", () => {
    it("remove_indices_out_of_range_noop", () => {
      const spec = addStage(emptySpec());
      const result = removeStage(spec, 99);

      expect(result).toEqual(spec);
    });

    it("removeStage_removes_correct", () => {
      let spec = emptySpec();
      spec = addStage(spec); // stage-1
      spec = addStage(spec); // stage-2
      spec = addStage(spec); // stage-3

      const removed = removeStage(spec, 1); // Remover stage-2

      expect(removed.stages).toHaveLength(2);
      expect(removed.stages[0].name).toBe("stage-1");
      expect(removed.stages[1].name).toBe("stage-3");
    });
  });

  describe("addJob - nested operations", () => {
    it("nested_add_update", () => {
      let spec = emptySpec();
      spec = addStage(spec); // stage-1
      spec = addJob(spec, 0); // job-1 dentro de stage-1
      spec = addStep(spec, 0, 0); // step-1 dentro de job-1

      // Actualizar el script del step
      spec = updateStep(spec, 0, 0, 0, { script: "make build" });

      expect(spec.stages[0].jobs[0].steps[0].script).toBe("make build");
      expect(spec.stages[0].jobs[0].steps[0].name).toBe("step-1");
    });
  });

  describe("removeJob y removeStep", () => {
    it("removeJob_out_of_range_noop", () => {
      let spec = emptySpec();
      spec = addStage(spec);
      spec = addJob(spec, 0);

      const result = removeJob(spec, 0, 99);
      expect(result).toEqual(spec);
    });

    it("removeStep_out_of_range_noop", () => {
      let spec = emptySpec();
      spec = addStage(spec);
      spec = addJob(spec, 0);
      spec = addStep(spec, 0, 0);

      const result = removeStep(spec, 0, 0, 99);
      expect(result).toEqual(spec);
    });
  });

  describe("moveJob y moveStep", () => {
    it("moveJob_out_of_range_noop", () => {
      let spec = emptySpec();
      spec = addStage(spec);
      spec = addJob(spec, 0);
      spec = addJob(spec, 0);

      const result = moveJob(spec, 0, 99, -1);
      expect(result).toEqual(spec);
    });

    it("moveStep_out_of_range_noop", () => {
      let spec = emptySpec();
      spec = addStage(spec);
      spec = addJob(spec, 0);
      spec = addStep(spec, 0, 0);
      spec = addStep(spec, 0, 0);

      const result = moveStep(spec, 0, 0, 99, -1);
      expect(result).toEqual(spec);
    });
  });

  describe("toSpecDict - limpia nulls/undefined", () => {
    it("toSpecDict_omits_nullish", () => {
      const spec: PipelineSpecDraft = {
        name: "test",
        stages: [{
          name: "s1",
          jobs: [{
            name: "j1",
            steps: [{
              name: "st1",
              script: "echo",
              env: {},
              // condition undefined → omitido
              working_directory: null, // null → omitido
            }],
            runner_tags: [],
            variables: {},
            artifacts: [],
            services: [],
            // image undefined → omitido
          }],
        }],
        variables: {},
        trigger_branches: [],
      };

      const dict = toSpecDict(spec);

      // Keys nullish se omiten
      expect("condition" in (dict.stages as any)[0].jobs[0].steps[0]).toBe(false);
      expect("working_directory" in (dict.stages as any)[0].jobs[0].steps[0]).toBe(false);
      expect("image" in (dict.stages as any)[0].jobs[0]).toBe(false);
    });
  });

  describe("fromParsedSpec - hidrata desde parse-yaml", () => {
    it("import_hydrates_from_parse_result", () => {
      // Fixture literal del roundtrip de F1 (respuesta de /api/devops/parse-yaml)
      const parseResult = {
        spec: {
          name: "my-pipeline",
          stages: [{
            name: "build",
            jobs: [{
              name: "build-job",
              steps: [{
                name: "compile",
                script: "echo build",
                env: {},
                condition: null,
                working_directory: null,
              }],
              image: "ubuntu:latest",
              pool_vm_image: null,
              runner_tags: [],
              variables: {},
              artifacts: [],
              services: [],
            }],
            condition: null,
          }],
          variables: {},
          trigger_branches: [],
          raw_yaml: "stages:\n  ...",
          raw_yaml_target: "gitlab",
        },
      };

      const draft = fromParsedSpec((parseResult as any).spec);

      expect(draft.name).toBe("my-pipeline");
      expect(draft.stages).toHaveLength(1);
      expect(draft.stages[0].name).toBe("build");
      expect(draft.stages[0].jobs[0].name).toBe("build-job");
      expect(draft.stages[0].jobs[0].steps[0].name).toBe("compile");
      expect(draft.raw_yaml).toBe("stages:\n  ...");
      expect(draft.raw_yaml_target).toBe("gitlab");
    });
  });

  describe("mergeDraftsIntoProfile - FIX C1", () => {
    it("mergeDrafts_preserves_foreign_keys", () => {
      const profile = {
        process_catalog: [{ kind: "batch" }],
        otra_key: 1,
      };
      const drafts = [{ name: "draft1", spec: { name: "d1", stages: [] }, updated_at: "2026-07-03T12:00:00Z" }];

      const merged = mergeDraftsIntoProfile(profile, drafts);

      // Keys ajenas INTACTAS
      expect(merged.process_catalog).toEqual([{ kind: "batch" }]);
      expect(merged.otra_key).toBe(1);

      // Key nueva agregada
      expect(merged.devops_pipeline_drafts).toEqual(drafts);

      // Objeto NUEVO (no mutó el input)
      expect(merged).not.toBe(profile);
    });

    it("mergeDrafts_null_profile", () => {
      const drafts = [{ name: "draft1", spec: { name: "d1", stages: [] }, updated_at: "2026-07-03T12:00:00Z" }];

      const merged = mergeDraftsIntoProfile(null, drafts);

      expect(merged).toEqual({
        devops_pipeline_drafts: drafts,
      });
    });
  });

  describe("starterSpec - C11", () => {
    it("starterSpec_valid_and_zero_local_errors", () => {
      const spec = starterSpec();

      // Tiene exactamente 1 stage / 1 job / 1 step con script no vacío
      expect(spec.stages).toHaveLength(1);
      expect(spec.stages[0].jobs).toHaveLength(1);
      expect(spec.stages[0].jobs[0].steps).toHaveLength(1);
      expect(spec.stages[0].jobs[0].steps[0].script).toBeTruthy();

      // Cero errores de validación local
      expect(validateSpecLocal(spec)).toEqual([]);
    });
  });

  describe("validateSpecLocal - C12", () => {
    it("validateSpecLocal_empty_spec_errors", () => {
      const spec = emptySpec();
      const errors = validateSpecLocal(spec);

      // Reglas 1 y 2: nombre y stage
      expect(errors).toContainEqual("El pipeline necesita un nombre");
      expect(errors.some((e) => e.includes("Agregá al menos un stage"))).toBe(true);
    });

    it("validateSpecLocal_nested_errors", () => {
      // Stage sin jobs + job sin steps
      const spec: PipelineSpecDraft = {
        name: "p",
        stages: [
          { name: "s1", jobs: [] }, // stage sin jobs
          {
            name: "s2",
            jobs: [{
              name: "j1",
              steps: [], // job sin steps
              runner_tags: [],
              variables: {},
              artifacts: [],
              services: [],
            }],
          },
        ],
        variables: {},
        trigger_branches: [],
      };

      const errors = validateSpecLocal(spec);

      // Stage sin jobs
      expect(errors.some((e) => e.includes("s1") && e.includes("no tiene jobs"))).toBe(true);

      // Job sin steps
      expect(errors.some((e) => e.includes("j1") && e.includes("no tiene steps"))).toBe(true);
    });

    it("validateSpecLocal_step_script_empty", () => {
      const spec: PipelineSpecDraft = {
        name: "p",
        stages: [{
          name: "s1",
          jobs: [{
            name: "j1",
            steps: [{
              name: "st1",
              script: "", // vacío
              env: {},
            }],
            runner_tags: [],
            variables: {},
            artifacts: [],
            services: [],
          }],
        }],
        variables: {},
        trigger_branches: [],
      };

      const errors = validateSpecLocal(spec);

      expect(errors.some((e) => e.includes("st1") && e.includes("no tiene script"))).toBe(true);
    });

    it("validateSpecLocal_complete_no_errors", () => {
      const spec: PipelineSpecDraft = {
        name: "p",
        stages: [{
          name: "s1",
          jobs: [{
            name: "j1",
            steps: [{
              name: "st1",
              script: "echo test",
              env: {},
            }],
            runner_tags: [],
            variables: {},
            artifacts: [],
            services: [],
          }],
        }],
        variables: {},
        trigger_branches: [],
      };

      const errors = validateSpecLocal(spec);

      expect(errors).toEqual([]);
    });

    it("validateSpecLocal_raw_yaml_target_invalid", () => {
      const spec: PipelineSpecDraft = {
        name: "p",
        stages: [{
          name: "s1",
          jobs: [{
            name: "j1",
            steps: [{
              name: "st1",
              script: "echo",
              env: {},
            }],
            runner_tags: [],
            variables: {},
            artifacts: [],
            services: [],
          }],
        }],
        variables: {},
        trigger_branches: [],
        raw_yaml: "stages: ...",
        raw_yaml_target: "invalid" as any, // Regla 6
      };

      const errors = validateSpecLocal(spec);

      expect(errors.some((e) => e.includes("Target de YAML crudo inválido"))).toBe(true);
    });
  });

  describe("specsEqual - C15", () => {
    it("specsEqual_detects_changes", () => {
      const spec = starterSpec();
      expect(specsEqual(spec, spec)).toBe(true);

      const modified = updateStep(spec, 0, 0, 0, { script: "x" });
      expect(specsEqual(spec, modified)).toBe(false);
    });

    it("specsEqual_normalizes_nullish", () => {
      const spec1: PipelineSpecDraft = {
        name: "p",
        stages: [{
          name: "s1",
          jobs: [{
            name: "j1",
            steps: [{
              name: "st1",
              script: "echo",
              env: {},
              working_directory: undefined, // undefined vs null
            }],
            runner_tags: [],
            variables: {},
            artifacts: [],
            services: [],
          }],
        }],
        variables: {},
        trigger_branches: [],
      };

      const spec2 = { ...spec1 };
      (spec2.stages[0] as any).jobs[0].steps[0].working_directory = null;

      // toSpecDict normaliza omitiendo undefined/null, así que son iguales
      expect(specsEqual(spec1, spec2)).toBe(true);
    });
  });
});

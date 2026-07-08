/**
 * Tests de pipelinePresets.ts - Plan 97 F0
 * TDD: catálogo estático de presets de pipeline por stack (sin React)
 */
import { describe, it, expect } from "vitest";
import { validateSpecLocal, starterSpec } from "./specBuilder";
import { PIPELINE_PRESETS, getPresetById, type PresetId, type StackId } from "./pipelinePresets";

const STACK_IDS: readonly StackId[] = ["dotnet", "node", "python", "go", "rust", "java", "php", "generic"];

describe("pipelinePresets - F0 TDD", () => {
  it("all_presets_have_unique_ids", () => {
    const ids = PIPELINE_PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(["python", "node", "dotnet", "generic"]);
  });

  it("every_preset_builds_valid_spec", () => {
    for (const preset of PIPELINE_PRESETS) {
      const spec = preset.build();
      expect(spec.name.trim()).not.toBe("");
      expect(spec.stages.length).toBeGreaterThanOrEqual(1);
      for (const stage of spec.stages) {
        expect(stage.jobs.length).toBeGreaterThanOrEqual(1);
        for (const job of stage.jobs) {
          expect(job.steps.length).toBeGreaterThanOrEqual(1);
          for (const step of job.steps) {
            expect(step.script.trim()).not.toBe("");
          }
        }
      }
    }
  });

  it("every_preset_passes_local_validation", () => {
    for (const preset of PIPELINE_PRESETS) {
      expect(validateSpecLocal(preset.build())).toEqual([]);
    }
  });

  it("python_preset_has_no_echo_placeholder", () => {
    const placeholder = starterSpec().stages[0].jobs[0].steps[0].script;
    const pythonSpec = getPresetById("python").build();
    for (const stage of pythonSpec.stages) {
      for (const job of stage.jobs) {
        for (const step of job.steps) {
          expect(step.script).not.toBe(placeholder);
        }
      }
    }
  });

  it("node_and_dotnet_presets_have_no_echo_placeholder", () => {
    const placeholder = starterSpec().stages[0].jobs[0].steps[0].script;
    for (const id of ["node", "dotnet"] as PresetId[]) {
      const spec = getPresetById(id).build();
      for (const stage of spec.stages) {
        for (const job of stage.jobs) {
          for (const step of job.steps) {
            expect(step.script).not.toBe(placeholder);
          }
        }
      }
    }
  });

  it("generic_preset_is_the_only_one_with_echo", () => {
    const hasEcho = (id: PresetId): boolean => {
      const spec = getPresetById(id).build();
      return spec.stages.some((s) =>
        s.jobs.some((j) => j.steps.some((st) => st.script.startsWith("echo ")))
      );
    };
    for (const preset of PIPELINE_PRESETS) {
      if (preset.id === "generic") {
        expect(hasEcho(preset.id)).toBe(true);
      } else {
        expect(hasEcho(preset.id)).toBe(false);
      }
    }
  });

  it("build_is_pure_and_immutable", () => {
    for (const preset of PIPELINE_PRESETS) {
      const a = preset.build();
      const b = preset.build();
      expect(a).not.toBe(b);
      expect(a).toEqual(b);
    }
  });

  it("getPresetById_unknown_throws", () => {
    expect(() => getPresetById("foo" as PresetId)).toThrow();
  });

  it("getPresetById_known_returns_preset", () => {
    expect(getPresetById("python").id).toBe("python");
  });

  // Plan 104 F0 — clasificación por stack
  it("every_preset_has_stack_field", () => {
    for (const preset of PIPELINE_PRESETS) {
      expect(STACK_IDS).toContain(preset.stack);
    }
  });

  it("stack_field_matches_id", () => {
    expect(getPresetById("python").stack).toBe("python");
    expect(getPresetById("node").stack).toBe("node");
    expect(getPresetById("dotnet").stack).toBe("dotnet");
    expect(getPresetById("generic").stack).toBe("generic");
  });
});

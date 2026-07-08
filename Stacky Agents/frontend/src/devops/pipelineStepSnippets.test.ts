/**
 * Tests de pipelineStepSnippets.ts - Plan 97 F1-bis (+ ampliación F1-ter)
 * TDD: biblioteca estática de acciones de pipeline prehechas (sin React)
 */
import { describe, it, expect } from "vitest";
import { emptySpec, addStage, addJob, appendStep, validateSpecLocal } from "./specBuilder";
import {
  PIPELINE_STEP_SNIPPETS,
  SNIPPET_CATEGORIES,
  getSnippetsByCategory,
  filterSnippetsByStack,
  STACK_OPTIONS,
  isStackId,
} from "./pipelineStepSnippets";
import type { StackId } from "./pipelinePresets";

const KNOWN_STACKS: readonly StackId[] = ["dotnet", "node", "python", "go", "rust", "java", "php", "generic"];

describe("pipelineStepSnippets - F1-bis TDD", () => {
  it("all_snippets_have_unique_ids", () => {
    const ids = PIPELINE_STEP_SNIPPETS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("at_least_20_snippets", () => {
    expect(PIPELINE_STEP_SNIPPETS.length).toBeGreaterThanOrEqual(20);
  });

  it("at_least_60_snippets", () => {
    // v4 (C3) — el catálogo sube a >=60 (conteo real 63) con la categoría infra.
    expect(PIPELINE_STEP_SNIPPETS.length).toBeGreaterThanOrEqual(60);
  });

  it("snippet_categories_include_seguridad_versionar_infra", () => {
    for (const cat of ["seguridad", "versionar", "infra"] as const) {
      expect(SNIPPET_CATEGORIES).toContain(cat);
      expect(getSnippetsByCategory(cat).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("every_snippet_builds_valid_step", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      const step = snip.build();
      expect(step.name.trim()).not.toBe("");
      expect(step.script.trim()).not.toBe("");
      expect(typeof step.env).toBe("object");
    }
  });

  it("no_snippet_uses_echo_or_ado_macro", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      const script = snip.build().script;
      expect(script.startsWith("echo ")).toBe(false);
      expect(script.includes("$(")).toBe(false);
    }
  });

  it("every_snippet_script_is_single_line", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      const script = snip.build().script;
      expect(script.includes("\n")).toBe(false);
      expect(script.includes("\r")).toBe(false);
    }
  });

  it("every_snippet_category_is_declared", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      expect(SNIPPET_CATEGORIES).toContain(snip.category);
    }
  });

  it("getSnippetsByCategory_covers_all", () => {
    const reconstructed = SNIPPET_CATEGORIES.flatMap((c) => getSnippetsByCategory(c));
    expect(reconstructed.length).toBe(PIPELINE_STEP_SNIPPETS.length);
    expect(new Set(reconstructed.map((s) => s.id))).toEqual(
      new Set(PIPELINE_STEP_SNIPPETS.map((s) => s.id))
    );
  });

  it("build_is_pure_and_immutable", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      const a = snip.build();
      const b = snip.build();
      expect(a).not.toBe(b);
      expect(a).toEqual(b);
    }
  });

  it("appendStep_inserts_snippet_and_keeps_spec_valid", () => {
    const base = addJob(addStage(emptySpec()), 0);
    const withName = { ...base, name: "p" };
    const snip = PIPELINE_STEP_SNIPPETS[0];
    const result = appendStep(withName, 0, 0, snip.build());
    expect(result).not.toBe(withName);
    expect(withName.stages[0].jobs[0].steps).toHaveLength(0); // original intacto
    expect(result.stages[0].jobs[0].steps).toHaveLength(1);
    expect(result.stages[0].jobs[0].steps[0].name).toBe(snip.build().name);
    expect(validateSpecLocal(result)).not.toContain(`El job '${result.stages[0].jobs[0].name}' no tiene steps`);
  });

  it("snippet_metadata_never_leaks_into_step", () => {
    const allowed = new Set(["name", "script", "env", "working_directory", "condition"]);
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      const keys = Object.keys(snip.build());
      for (const k of keys) {
        expect(allowed.has(k)).toBe(true);
      }
    }
  });

  it("snippets_with_hardcoded_literal_are_flagged_needs_edit", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      if (snip.build().script.includes("myapp:latest")) {
        expect(snip.needsEdit).toBe(true);
      }
    }
  });

  // Plan 104 F0 — clasificación por stack + filtro
  it("every_snippet_has_stacks_array", () => {
    for (const snip of PIPELINE_STEP_SNIPPETS) {
      expect(Array.isArray(snip.stacks)).toBe(true);
    }
  });

  it("filterSnippetsByStack_all_returns_everything", () => {
    expect(filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, "all")).toHaveLength(PIPELINE_STEP_SNIPPETS.length);
  });

  it("filterSnippetsByStack_dotnet_excludes_python", () => {
    const filtered = filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, "dotnet");
    for (const s of filtered) {
      const script = s.build().script;
      expect(script.includes("pip ")).toBe(false);
      expect(script.includes("pytest")).toBe(false);
    }
  });

  it("filterSnippetsByStack_python_excludes_dotnet", () => {
    const filtered = filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, "python");
    for (const s of filtered) {
      expect(s.build().script.includes("dotnet")).toBe(false);
    }
  });

  it("generic_snippets_have_empty_stacks", () => {
    const generic = PIPELINE_STEP_SNIPPETS.filter((s) => s.build().script.includes("docker") || s.id.startsWith("infra-"));
    for (const s of generic) {
      expect(s.stacks).toEqual([]);
    }
  });

  it("at_least_one_snippet_per_known_stack", () => {
    for (const stack of KNOWN_STACKS) {
      expect(filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, stack).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("isStackId_rejects_unknown", () => {
    expect(isStackId("kotlin")).toBe(false);
    expect(isStackId("python")).toBe(true);
    expect(isStackId(null)).toBe(false);
    expect(isStackId(undefined)).toBe(false);
    expect(STACK_OPTIONS).toContain("all");
  });
});

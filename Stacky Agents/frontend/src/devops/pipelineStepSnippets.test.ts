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
} from "./pipelineStepSnippets";

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
});

/**
 * Tests de pipelineRecipes.ts - Plan 97 F1-ter
 * TDD: recetas = bundles ordenados de acciones prehechas (sin React)
 */
import { describe, it, expect } from "vitest";
import { emptySpec, addStage, addJob, appendStep, validateSpecLocal } from "./specBuilder";
import { PIPELINE_STEP_SNIPPETS } from "./pipelineStepSnippets";
import { PIPELINE_RECIPES, buildRecipeSteps, type StepRecipe } from "./pipelineRecipes";

describe("pipelineRecipes - F1-ter TDD", () => {
  it("all_recipes_have_unique_ids", () => {
    const ids = PIPELINE_RECIPES.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("at_least_10_recipes", () => {
    expect(PIPELINE_RECIPES.length).toBeGreaterThanOrEqual(10);
  });

  it("ci_recipes_cover_rust_java_php", () => {
    const ids = PIPELINE_RECIPES.map((r) => r.id);
    expect(ids).toContain("ci-rust");
    expect(ids).toContain("ci-java-maven");
    expect(ids).toContain("ci-php");
  });

  it("every_recipe_references_existing_snippets", () => {
    const knownIds = new Set(PIPELINE_STEP_SNIPPETS.map((s) => s.id));
    for (const recipe of PIPELINE_RECIPES) {
      for (const stepId of recipe.stepIds) {
        expect(knownIds.has(stepId)).toBe(true);
      }
    }
  });

  it("every_recipe_has_at_least_two_steps", () => {
    for (const recipe of PIPELINE_RECIPES) {
      expect(recipe.stepIds.length).toBeGreaterThanOrEqual(2);
    }
  });

  it("buildRecipeSteps_returns_valid_steps", () => {
    for (const recipe of PIPELINE_RECIPES) {
      const steps = buildRecipeSteps(recipe);
      expect(steps).toHaveLength(recipe.stepIds.length);
      for (const st of steps) {
        expect(st.name.trim()).not.toBe("");
        expect(st.script.trim()).not.toBe("");
      }
    }
  });

  it("buildRecipeSteps_unknown_snippet_throws", () => {
    const fake: StepRecipe = { id: "fake", label: "Fake", description: "x", stepIds: ["no-existe"] };
    expect(() => buildRecipeSteps(fake)).toThrow();
  });

  it("inserting_recipe_into_empty_job_keeps_spec_valid", () => {
    const base = { ...addJob(addStage(emptySpec()), 0), name: "p" };
    const recipe = PIPELINE_RECIPES[0];
    const steps = buildRecipeSteps(recipe);
    const result = steps.reduce((acc, st) => appendStep(acc, 0, 0, st), base);
    expect(base.stages[0].jobs[0].steps).toHaveLength(0); // original intacto
    expect(result.stages[0].jobs[0].steps).toHaveLength(steps.length);
    expect(validateSpecLocal(result)).toEqual([]);
  });

  it("inserting_recipe_into_non_empty_job_appends", () => {
    const withOneStep = appendStep(
      { ...addJob(addStage(emptySpec()), 0), name: "p" },
      0, 0, { name: "ya-existente", script: "echo existente", env: {} }
    );
    const recipe = PIPELINE_RECIPES.find((r) => r.stepIds.length >= 2)!;
    const steps = buildRecipeSteps(recipe);
    const result = steps.reduce((acc, st) => appendStep(acc, 0, 0, st), withOneStep);
    expect(result.stages[0].jobs[0].steps).toHaveLength(1 + steps.length);
    expect(validateSpecLocal(result)).toEqual([]);
  });
});

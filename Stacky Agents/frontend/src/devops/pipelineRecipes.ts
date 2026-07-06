/**
 * pipelineRecipes.ts — Plan 97 F1-ter
 * Recetas = bundles ORDENADOS de acciones prehechas que se insertan de una en un
 * job. NO duplican scripts: referencian snippets de pipelineStepSnippets.ts por
 * id y reusan el helper inmutable appendStep.
 */
import type { StepDraft } from "./specBuilder";
import { PIPELINE_STEP_SNIPPETS } from "./pipelineStepSnippets";

export interface StepRecipe {
  id: string;
  label: string;
  description: string;
  stepIds: readonly string[];  // ids EXISTENTES de PIPELINE_STEP_SNIPPETS, en orden
}

export const PIPELINE_RECIPES: readonly StepRecipe[] = [
  { id: "ci-python", label: "CI Python completo", description: "pip install, flake8 y pytest con cobertura.", stepIds: ["dep-pip-install", "lint-flake8", "test-pytest-cov"] },
  { id: "ci-node", label: "CI Node completo", description: "npm ci, lint, test y build.", stepIds: ["dep-npm-ci", "lint-eslint", "test-npm-test", "build-npm"] },
  { id: "ci-dotnet", label: "CI .NET completo", description: "restore, build Release y test.", stepIds: ["dep-dotnet-restore", "build-dotnet-release", "test-dotnet"] },
  { id: "ci-go", label: "CI Go completo", description: "vet, build y test de Go.", stepIds: ["lint-go-vet", "build-go", "test-go"] },
  { id: "docker-build-push", label: "Docker build + push", description: "Construye y publica la imagen (editá el tag).", stepIds: ["build-docker", "pub-docker-push"] },
  { id: "quality-python", label: "Calidad Python", description: "ruff, black --check, pytest con cobertura y reporte.", stepIds: ["lint-ruff", "lint-black-check", "test-pytest-cov", "qual-coverage-report"] },
  // ── v4 C1 — recetas por stack faltantes (Rust/Java/PHP) + auditoría de seguridad ──
  { id: "ci-rust", label: "CI Rust completo", description: "fetch, clippy, build release y test.", stepIds: ["dep-cargo-fetch", "lint-cargo-clippy", "build-cargo-release", "test-cargo"] },
  { id: "ci-java-maven", label: "CI Java (Maven) completo", description: "package sin tests y verify.", stepIds: ["build-maven", "test-maven"] },
  { id: "ci-php", label: "CI PHP completo", description: "composer install y PHPUnit.", stepIds: ["dep-composer-install", "test-phpunit"] },
  { id: "sec-audit-node", label: "Auditoría de seguridad Node", description: "npm ci y npm audit.", stepIds: ["dep-npm-ci", "sec-npm-audit"] },
  { id: "sec-audit-python", label: "Auditoría de seguridad Python", description: "pip install y pip-audit.", stepIds: ["dep-pip-install", "sec-pip-audit"] },
];

export function buildRecipeSteps(recipe: StepRecipe): StepDraft[] {
  return recipe.stepIds.map((id) => {
    const snip = PIPELINE_STEP_SNIPPETS.find((s) => s.id === id);
    if (!snip) throw new Error(`Receta '${recipe.id}' referencia snippet inexistente: ${id}`);
    return snip.build();
  });
}

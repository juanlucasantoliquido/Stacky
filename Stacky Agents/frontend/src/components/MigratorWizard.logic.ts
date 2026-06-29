/**
 * Plan 74 F7 — Lógica pura del wizard de migración (sin UI).
 *
 * Exporta tipos y funciones puras que el componente MigratorWizard.tsx consume.
 * Al ser código puramente funcional (sin JSX/hooks), puede testearse con Node/ts-node.
 */

export type WizardStep = "select" | "plan" | "confirm" | "execute" | "done";

export interface MigrationPlanSummary {
  plan_id: string;
  plan_hash: string;
  total_ops: number;
  counts_by_type: Record<string, number>;
  warnings: string[];
  skipped_at_plan: number;
}

export interface MigrationRunResult {
  applied: number;
  skipped: number;
  failed: Array<{ ado_id: string; op_kind: string; error: string }>;
  orphaned: string[];
}

export type WizardState =
  | { step: "select"; stacky_project: string; epic_policy: string }
  | { step: "plan"; stacky_project: string; epic_policy: string; plan: MigrationPlanSummary }
  | { step: "confirm"; stacky_project: string; plan: MigrationPlanSummary }
  | { step: "execute"; stacky_project: string; plan: MigrationPlanSummary }
  | { step: "done"; stacky_project: string; plan: MigrationPlanSummary; result: MigrationRunResult };

/**
 * Avanza el wizard al siguiente paso.
 * Pura: no tiene efectos secundarios.
 */
export function nextStep(state: WizardState): WizardStep {
  const steps: WizardStep[] = ["select", "plan", "confirm", "execute", "done"];
  const idx = steps.indexOf(state.step);
  return steps[Math.min(idx + 1, steps.length - 1)];
}

/**
 * Devuelve el índice del paso actual (para barra de progreso).
 */
export function stepIndex(step: WizardStep): number {
  const steps: WizardStep[] = ["select", "plan", "confirm", "execute", "done"];
  return steps.indexOf(step);
}

/** Número total de pasos del wizard. */
export const TOTAL_STEPS = 5;

/**
 * Label legible por humano para cada paso.
 */
export function stepLabel(step: WizardStep): string {
  const labels: Record<WizardStep, string> = {
    select: "Configurar origen",
    plan: "Vista previa del plan",
    confirm: "Confirmacion HITL",
    execute: "Ejecutando",
    done: "Completado",
  };
  return labels[step];
}

/**
 * Determina si la migración tiene advertencias que requieren atención extra del operador.
 */
export function hasHighRiskWarnings(plan: MigrationPlanSummary): boolean {
  return plan.warnings.some((w) =>
    w.toLowerCase().includes("huerfano") || w.toLowerCase().includes("orphan")
  );
}

/**
 * Resumen de resultados formateado para el operador.
 */
export function formatRunSummary(result: MigrationRunResult): string {
  const parts = [
    `Aplicadas: ${result.applied}`,
    `Omitidas: ${result.skipped}`,
  ];
  if (result.failed.length > 0) {
    parts.push(`Fallidas: ${result.failed.length}`);
  }
  if (result.orphaned.length > 0) {
    parts.push(`Huerfanas: ${result.orphaned.length}`);
  }
  return parts.join(" | ");
}

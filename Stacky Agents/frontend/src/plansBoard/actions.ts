import type { RuntimeModelCatalog } from "../api/endpoints";

/** Plan 196 — helpers puros de las acciones HITL del pipeline de planes.
 *  Sin DOM, sin red: todo lo testeable del panel vive acá (G10). */

export type PipelineAction = "proponer" | "criticar" | "implementar" | "supervisar";

export const ACTION_LABEL: Record<PipelineAction, string> = {
  proponer: "Proponer plan nuevo",
  criticar: "Criticar este plan",
  implementar: "Implementar este plan",
  supervisar: "Supervisar este plan",
};

export const RUNTIME_ACTION_NOTE =
  "Las acciones del pipeline usan las skills de Claude Code del repo; Codex y Copilot no las tienen. La visualización del tablero sí es idéntica en los 3 runtimes.";

/** Espejo EXACTO de allowed_actions_for del backend (§4.3). */
export function allowedActionsForCard(
  estado: string,
  docDrift: boolean | null | undefined
): PipelineAction[] {
  const acts: PipelineAction[] = [];
  if (estado === "PROPUESTO") acts.push("criticar");
  if (estado === "CRITICADO") acts.push("implementar");
  if (estado === "IMPLEMENTADO" || estado === "IMPLEMENTADO_PARCIAL" || docDrift === true) {
    acts.push("supervisar");
  }
  return acts;
}

/** Efforts válidos para un modelo según effort_support del catálogo (159).
 * Matriz vacía o modelo desconocido → TODOS los efforts del runtime (fallback
 * permisivo: el backend re-clampa igual). */
export function effortsForModel(
  rt: RuntimeModelCatalog | undefined,
  modelId: string
): { id: string; label: string }[] {
  const all = rt?.efforts ?? [];
  const supported = rt?.effort_support?.[modelId];
  if (!supported || supported.length === 0) return all;
  return all.filter((e) => supported.includes(e.id));
}

export interface RunPipelineActionPayload {
  action: PipelineAction;
  plan_number: number | null;
  idea: string | null;
  model: string | null;
  effort: string | null;
  runtime: "claude_code_cli";
}

export function buildRunPayload(
  action: PipelineAction,
  planNumber: number | null,
  idea: string,
  model: string,
  effort: string
): RunPipelineActionPayload {
  return {
    action,
    plan_number: action === "proponer" ? null : planNumber,
    idea: action === "proponer" && idea.trim() ? idea.trim() : null,
    model: model || null,
    effort: effort || null,
    runtime: "claude_code_cli",
  };
}

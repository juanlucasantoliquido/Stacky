import type { ModelCatalogResponse, RuntimeModelCatalog } from "../api/endpoints";

/** Plan 159 — ÚNICO fallback embebido del lado frontend. Reemplaza las 3
 * listas locales de IncidentResolverModal / EpicFromBriefModal /
 * ModelDecisionChip. Su gemelo backend es _EMERGENCY_FALLBACK en
 * services/model_catalog.py (uno por lado de la red, C5). */
export const EMERGENCY_MODEL_CATALOG: Record<string, RuntimeModelCatalog> = {
  claude_code_cli: {
    source: "emergency_fallback",
    default_model: "claude-sonnet-5",
    default_effort: "medium",
    models: [
      { id: "claude-sonnet-5", label: "Sonnet 5 (recomendado)", recommended: true },
      { id: "claude-opus-4-8", label: "Opus 4.8", recommended: false },
      { id: "claude-haiku-4-5", label: "Haiku 4.5", recommended: false },
    ],
    efforts: [{ id: "medium", label: "medium" }],
    effort_support: {},
  },
};

/** Función pura, testeable sin DOM: decide qué catálogo mostrar.
 * C7: merge POR RUNTIME — si claude viene vacío se reemplaza SOLO
 * claude_code_cli por el de emergencia, preservando datos vivos de los
 * demás runtimes (p. ej. introspección copilot). */
export function resolveModelCatalog(
  apiResult: ModelCatalogResponse | null | undefined
): Record<string, RuntimeModelCatalog> {
  if (!apiResult || !apiResult.ok) return EMERGENCY_MODEL_CATALOG;
  const rt = (apiResult.runtimes || {}) as Record<string, RuntimeModelCatalog>;
  const hasClaudeModels = (rt.claude_code_cli?.models?.length ?? 0) > 0;
  if (!hasClaudeModels) {
    return { ...rt, claude_code_cli: EMERGENCY_MODEL_CATALOG.claude_code_cli };
  }
  return rt;
}

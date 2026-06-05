// resolveSuggestedAgent — fuente única de la lógica de "Run Sugerido" (B5).
//
// Antes la sugerencia para tickets no-EPIC salía EXCLUSIVAMENTE de FlowConfig
// keyeado por `ado_state`. Si el estado del ticket no estaba mapeado (ej. un
// Feature/Technical en "To Do" o "Committed") la sugerencia era `null` y el
// botón quedaba deshabilitado → "solo sugiere en EPIC". Este resolver agrega
// dos fallbacks y unifica la lógica que estaba DUPLICADA entre la vista árbol
// (TicketBoard.tsx) y la vista grafo (TicketGraphView.jsx), que además
// divergían en la regla de supresión de "business".
//
// Orden de resolución:
//   (1) FlowConfig por estado  — señal explícita del operador (máxima prioridad).
//   (2) pipeline_summary.next_suggested — la cadena que ya calcula el backend
//       (business→functional→technical→developer→qa) y viaja en cada ticket.
//   (3) Fallback por tipo de work item — para estados no mapeados sin pipeline.
//
// Regla de negocio preservada: Tasks y Épicas nunca proponen "Negocio" (ya
// tienen análisis previo). Pero en vez de forzar `null` (que dejaba al ticket
// sin ninguna sugerencia), ahora CAE al siguiente fallback.

export interface ResolveSuggestedAgentInput {
  workItemType?: string | null;
  adoState?: string | null;
  /** Mapa ado_state(lowercase) → agent_type construido desde FlowConfig. */
  flowConfigMap: Map<string, string>;
  /** ticket.pipeline_summary?.next_suggested del backend. */
  pipelineNext?: string | null;
}

// Fallback final por tipo de work item (ver decisión D-B5 del plan). Mapa
// intencionalmente conservador; ajustable según el proceso ADO del cliente.
const TYPE_FALLBACK: Record<string, string> = {
  epic: "functional",
  feature: "technical",
  task: "developer",
  "user story": "developer",
  bug: "developer",
};

export function resolveSuggestedAgent({
  workItemType,
  adoState,
  flowConfigMap,
  pipelineNext,
}: ResolveSuggestedAgentInput): string | null {
  const type = (workItemType ?? "").trim().toLowerCase();
  const isTask = type === "task";
  const isEpic = type === "epic";

  // Tasks y Épicas nunca proponen Negocio: si un candidato resuelve a
  // "business" para esos tipos, lo descartamos para caer al siguiente fallback.
  const suppressBusiness = (cand: string | null): string | null =>
    cand === "business" && (isTask || isEpic) ? null : cand;

  // (1) FlowConfig por estado.
  const flow = adoState ? flowConfigMap.get(adoState.trim().toLowerCase()) ?? null : null;
  const flowResolved = suppressBusiness(flow);
  if (flowResolved) return flowResolved;

  // (2) Pipeline summary del backend.
  const pipe = suppressBusiness(pipelineNext ?? null);
  if (pipe) return pipe;

  // (3) Fallback por tipo de work item.
  return TYPE_FALLBACK[type] ?? null;
}

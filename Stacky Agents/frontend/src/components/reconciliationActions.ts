// Plan 269 F6 — qué acción ofrece cada discrepancia. PURO, sin fetch.
//
// RIEL DURO: Stacky NUNCA cambia un estado terminal por su cuenta. Este módulo
// solo decide QUÉ botón se ofrece; el cambio lo dispara un click del operador.
//
// RIEL DURO 2: la corrección va SIEMPRE a PATCH /api/tickets/{ticket_id}/stacky-status
// (backend/api/tickets.py:1166), que llama a ts.set_status y NO publica nada.
// Está PROHIBIDO el endpoint por ado_id (backend/api/tickets.py:1205) porque ese
// camino SÍ publica en Azure DevOps y SÍ cambia el estado del work item. Un test
// vigila que `correctionPath` no contenga "by-ado".

export interface ReconciliationItem {
  execution_id: number;
  ticket_id: number;
  kind: string;
  detail: string;
}

export interface ItemAction {
  label: string;          // texto del botón
  targetStatus: string;   // stacky_status al que se movería
  confirm: string;        // texto de la confirmación explícita
  reason: string;         // se manda en el body como `reason`
}

/** Marcador que `verdict_agreement()` (F8) cuenta para saber si el veredicto
 *  está calibrado. Si alguien reescribe el texto sin este prefijo, la
 *  calibración queda muda: hay un test que lo impide. */
export const CORRECTION_MARKER = "[269] corrección manual de falso rojo";

/** Solo 2 de los 5 DISCREPANCY_KINDS tienen una corrección obvia y segura.
 *  Los otros 3 devuelven null: se listan para que el humano mire, sin botón. */
export function actionForItem(item: ReconciliationItem): ItemAction | null {
  if (item.kind === "red_with_delivered_work") {
    return {
      label: "Marcar como terminado",
      targetStatus: "completed",
      confirm: `La incidencia #${item.ticket_id} figura como fallada pero entregó trabajo. ¿La marcás como terminada?`,
      reason: `${CORRECTION_MARKER} (execution ${item.execution_id})`,
    };
  }
  if (item.kind === "green_with_dirty_close") {
    return {
      label: "Marcar para revisión",
      targetStatus: "needs_review",
      confirm: `La incidencia #${item.ticket_id} figura como terminada sobre un cierre sucio. ¿La marcás para revisar?`,
      reason: `[269] cierre sucio confirmado por el operador (execution ${item.execution_id})`,
    };
  }
  return null;
}

/** La ruta EXACTA del endpoint permitido. Existe como función para que un test
 *  pueda asegurar que nadie escribió el camino que publica en el tracker. */
export function correctionPath(ticketId: number): string {
  return `/api/tickets/${ticketId}/stacky-status`;
}

/** Cap de filas que la card lista, para no volcar 200 líneas en una card de
 *  diagnóstico. */
export const MAX_RECONCILIATION_ROWS = 25;

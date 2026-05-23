/**
 * agentCompletionErrors.ts
 *
 * Mapeo canónico de error.code del gateway de finalización de agentes
 * a copy entendible para el operador.
 *
 * Reglas:
 * - Nunca mostrar stacktrace ni correlation_id en superficie.
 * - El correlation_id puede ir en data-attr del toast para soporte.
 * - severity: 'warning' = informativo recuperable; 'error' = bloqueo.
 */
export const AGENT_COMPLETION_ERROR_COPY = {
    payload_invalid: {
        title: "Datos inválidos",
        body: "La UI envió un payload mal formado. Reportá este error al equipo Stacky.",
        severity: "error",
    },
    auth_required: {
        title: "Sesión expirada",
        body: "Refrescá la página y volvé a intentar.",
        severity: "warning",
    },
    ticket_not_found: {
        title: "Ticket no encontrado",
        body: "El ticket ya no existe o cambió de identificador.",
        severity: "error",
    },
    no_active_execution: {
        title: "Sin ejecución activa",
        body: "No hay ejecución pendiente para cerrar. La inconsistencia puede haberse resuelto sola.",
        severity: "warning",
    },
    execution_state_invalid: {
        title: "Estado inválido",
        body: "La ejecución ya fue cerrada por otro proceso.",
        severity: "warning",
    },
    html_already_published: {
        title: "HTML ya publicado",
        body: "Ya existe un comentario publicado para esta ejecución. ¿Querés forzar la publicación de un HTML distinto?",
        severity: "warning",
    },
    html_invalid: {
        title: "HTML inválido",
        body: "El HTML del agente no pasa las reglas de validación. Quedó marcado como needs_review.",
        severity: "error",
    },
    internal_error: {
        title: "Error interno",
        body: "Falló el cierre. El equipo recibió la traza. Reintentá en unos minutos.",
        severity: "error",
    },
};
/** Fallback para error.code desconocido. */
export const UNKNOWN_ERROR_INFO = {
    title: "Error inesperado",
    body: "Ocurrió un error no clasificado. Contactá al equipo Stacky con el contexto de la acción.",
    severity: "error",
};
/**
 * Devuelve la info de copia para un error.code dado.
 * Nunca retorna undefined — si el código es desconocido, retorna UNKNOWN_ERROR_INFO.
 */
export function getErrorInfo(code) {
    if (!code)
        return UNKNOWN_ERROR_INFO;
    return AGENT_COMPLETION_ERROR_COPY[code] ?? UNKNOWN_ERROR_INFO;
}

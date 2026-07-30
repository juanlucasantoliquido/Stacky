/**
 * Plan 265 F5(b) — Degradación del panel Historial (D6): `GET
 * /api/executions/history` está gateado por `STACKY_EXECUTION_HISTORY_ENABLED`
 * y devuelve 404 `feature_disabled` cuando está OFF. `api.get` lanza ante
 * cualquier non-2xx, así que este panel se lee con `rawGet` (o try/catch) y
 * degrada con un motivo visible en vez de tumbar la consola entera. Lógica
 * pura, sin React.
 */

export interface HistoryPanelState {
  available: boolean;
  reason: string | null;
  items: unknown[];
}

/** Interpreta la respuesta cruda de `GET /api/executions/history` (leída con
 *  rawGet, nunca con `api.get`) y decide si el panel Historial tiene datos
 *  para mostrar o debe degradar con un motivo visible. Nunca lanza. */
export function historyPanelState(res: { status: number; body: unknown }): HistoryPanelState {
  const status = res?.status ?? 0;
  const body = res?.body;

  if (status >= 200 && status < 300) {
    const items = Array.isArray(body) ? body : [];
    return { available: true, reason: null, items };
  }

  if (status === 404 && body && typeof body === "object" && (body as Record<string, unknown>).error === "feature_disabled") {
    return {
      available: false,
      reason: "Historial no disponible: la capacidad está desactivada en la configuración.",
      items: [],
    };
  }

  return {
    available: false,
    reason: `No se pudo cargar el historial (código ${status}).`,
    items: [],
  };
}

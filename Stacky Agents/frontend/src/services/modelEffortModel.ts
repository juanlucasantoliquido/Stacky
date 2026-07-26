// Plan 212 F7 — "solicitado vs efectivo" como función pura.
// El backend escribe metadata.model_effort en cada run del CLI de Claude; acá
// se decide si hay algo que contarle al operador y con qué texto.

export interface ModelEffortTrace {
  requested_model?: string;
  effective_model?: string;
  requested_effort?: string;
  effective_effort?: string;
  downgraded?: boolean;
  reason?: string;
}

/** Combina modelo y effort en el par que el operador reconoce ("opus/xhigh"). */
function par(modelo?: string, effort?: string): string {
  const m = (modelo ?? "").trim();
  const e = (effort ?? "").trim();
  if (m && e) return `${m}/${e}`;
  return m || e || "automático";
}

/**
 * Devuelve la línea de advertencia, o null si no hay nada que advertir.
 *
 * Null en tres casos distintos que para el operador son el mismo: no hay traza
 * (runtime sin --model, ejecución vieja), o la traza dice que se cumplió.
 */
export function describeDowngrade(
  metadata: Record<string, unknown> | null | undefined
): string | null {
  const traza = metadata?.model_effort as ModelEffortTrace | undefined;
  if (!traza || typeof traza !== "object") return null;
  if (traza.downgraded !== true) return null;

  const solicitado = par(traza.requested_model, traza.requested_effort);
  const ejecutado = par(traza.effective_model, traza.effective_effort);
  const razon = (traza.reason ?? "").trim();

  const base = `Solicitado ${solicitado} → ejecutado ${ejecutado}`;
  return razon ? `${base} — ${razon}` : base;
}

// Plan 264 F6 — texto de historial "qué se usó de verdad" para los 3 runtimes.
//
// Distinto de modelEffortModel.ts (Plan 212 F7 describeDowngrade): ESE sólo
// devuelve algo cuando hubo degradación; ESTE siempre devuelve un resumen
// (tool + degradación + nota de effort_mode), para el drawer de detalle de
// ejecución. Nunca recalcula `downgraded`: lo lee tal cual lo escribe el
// backend (services/runtime_capabilities.build_model_effort_trace).

export interface ModelEffortTraceV264 {
  tool?: string;
  requested_model?: string;
  effective_model?: string;
  requested_effort?: string;
  effective_effort?: string;
  downgraded?: boolean;
  reason?: string;
  effort_mode?: string;
  effort_effective_now?: boolean;
  origen_model?: string;
  origen_effort?: string;
}

export interface FormattedModelEffortTrace {
  tool: string;
  degraded: boolean;
  text: string;
}

function par(modelo?: string, effort?: string): string {
  const m = (modelo ?? "").trim();
  const e = (effort ?? "").trim();
  if (m && e) return `${m}/${e}`;
  return m || e || "automático";
}

/** Nunca lanza. `null` si no hay traza (runtime sin trace, o deploy viejo
 * sin metadata.model_effort). */
export function formatModelEffortTrace(
  trace: ModelEffortTraceV264 | null | undefined
): FormattedModelEffortTrace | null {
  if (!trace || typeof trace !== "object") return null;

  // Deploy viejo (Plan 212, antes del 264): sin `tool` -> se muestra "—".
  const tool = trace.tool && trace.tool.trim() ? trace.tool : "—";
  const degraded = trace.downgraded === true;

  let text: string;
  if (trace.effort_mode === "no_aplica") {
    text = `${tool}: esta herramienta no usa niveles de esfuerzo.`;
  } else if (degraded) {
    const solicitado = par(trace.requested_model, trace.requested_effort);
    const ejecutado = par(trace.effective_model, trace.effective_effort);
    const razon = (trace.reason ?? "").trim();
    text = `${solicitado} → ${ejecutado}` + (razon ? ` — ${razon}` : "");
  } else {
    text = par(
      trace.effective_model || trace.requested_model,
      trace.effective_effort || trace.requested_effort
    );
  }

  // [C8] Codex sin cap de turnos: la elección quedó registrada pero hoy no
  // cambia la corrida — se lo decimos al operador en vez de fingir efecto.
  if (trace.effort_mode === "presupuesto_turnos" && trace.effort_effective_now === false) {
    text += " (el esfuerzo quedó registrado, pero hoy no cambia esta corrida: no hay límite de turnos configurado)";
  }

  return { tool, degraded, text };
}

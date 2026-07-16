// Plan 144 F4 — formatea metadata.stall (watchdog de inactividad) en un
// mensaje humano para el drawer de detalle de ejecución. Helper puro.
export interface StallMeta {
  detected_at?: string;
  last_event_at?: string;
  last_signal?: string;
  seconds_idle?: number;
  watchdog_seconds?: number;
  trust_ok?: boolean;
}

export function formatStallReason(stall: StallMeta | null | undefined): string | null {
  if (!stall) return null;
  const secs = stall.watchdog_seconds ?? stall.seconds_idle;
  const base = secs != null
    ? `Run terminado por inactividad (${secs}s sin eventos del stream).`
    : "Run terminado por inactividad del stream.";
  const signal = stall.last_signal && stall.last_signal !== "none"
    ? ` Última señal: ${stall.last_signal}.`
    : " Sin señales previas del agente.";
  const trust = stall.trust_ok === false
    ? " Posible causa: workspace no confiado (ver preflight de trust)."
    : "";
  return base + signal + trust;
}

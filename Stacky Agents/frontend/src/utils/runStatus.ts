export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";
// Debe coincidir con StatusChipProps["tone"] (138 §10.2). NO importar desde ui/ para no acoplar utils->ui.

interface StatusView { tone: StatusTone; label: string; }

const MAP: Record<string, StatusView> = {
  completed:    { tone: "success", label: "Completado" },
  success:      { tone: "success", label: "Completado" },
  done:         { tone: "success", label: "Completado" },
  running:      { tone: "info",    label: "En ejecución" },
  in_progress:  { tone: "info",    label: "En ejecución" },
  pending:      { tone: "neutral", label: "Pendiente" },
  queued:       { tone: "neutral", label: "En cola" },
  needs_review: { tone: "warning", label: "Requiere revisión" },
  review:       { tone: "warning", label: "Requiere revisión" },
  error:        { tone: "danger",  label: "Error" },
  failed:       { tone: "danger",  label: "Error" },
  cancelled:    { tone: "neutral", label: "Cancelado" },
  canceled:     { tone: "neutral", label: "Cancelado" },
};

function normalize(status: string | null | undefined): string {
  return String(status ?? "").trim().toLowerCase();
}

export function runStatusTone(status: string | null | undefined): StatusTone {
  return MAP[normalize(status)]?.tone ?? "neutral";
}

/** Etiqueta ES; si el status es desconocido devuelve el crudo; si viene vacío "—". */
export function runStatusLabel(status: string | null | undefined): string {
  const key = normalize(status);
  if (!key) return "—";
  return MAP[key]?.label ?? String(status);
}

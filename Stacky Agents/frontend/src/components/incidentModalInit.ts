/**
 * incidentModalInit.ts — Plan 188 F3.
 *
 * Helper puro (sin DOM) para resolver el estado inicial del
 * IncidentResolverModal. Con props opcionales ausentes reproduce EXACTAMENTE
 * el comportamiento actual (texto vacío, sin adjuntos) — KPI-4
 * retrocompatibilidad.
 */
export interface IncidentModalInit {
  text: string;
  files: File[];
}

export function resolveModalInit(
  initialText?: string,
  initialFiles?: File[],
): IncidentModalInit {
  return { text: initialText ?? '', files: initialFiles ?? [] };
}

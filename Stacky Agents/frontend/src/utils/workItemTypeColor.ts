/**
 * Plan 77 F5 — Color canónico por tipo de work item.
 *
 * Fuente única de verdad para los colores de work_item_type en la UI.
 * Todos los componentes que coloreen por tipo deben importar desde aquí.
 */

/** Mapa type → color hex. Insensible a mayúsculas al llamar getWorkItemTypeColor(). */
const WORK_ITEM_TYPE_COLORS: Record<string, string> = {
  issue:   "#FF3B5C", // rojo/carmesí vívido — Issue/Incidencia (S/L parecido a epic, hue desplazado 10° hacia magenta y 100% saturación para distinguirse de bug #EF4444 a simple vista)
  epic:    "#8B5CF6", // violeta — Epic
  task:    "#3B82F6", // azul — Task / User Story
  bug:     "#EF4444", // rojo — Bug
  feature: "#10B981", // verde — Feature
  // Plan 277 — las 3 fases del contrato de jerarquía. Los tokens son ASCII sin
  // acento (regla 1 del contrato); el ACENTO va solo en el rótulo visible.
  funcional:      "#F59E0B", // ámbar — Análisis Funcional
  tecnico:        "#06B6D4", // cian  — Análisis Técnico
  implementacion: "#3B82F6", // azul  — Implementación (comparte familia con task, es su ejecución)
};

/**
 * Plan 277 — Rótulo visible por tipo. El token que se guarda en la base es ASCII
 * sin acento (lo exige el contrato de etiquetas); el acento vive solo acá, que es
 * lo único que ve el operador.
 */
const WORK_ITEM_TYPE_LABELS: Record<string, string> = {
  epic:           "Épica",
  funcional:      "Análisis Funcional",
  tecnico:        "Análisis Técnico",
  implementacion: "Implementación",
};

/** Color por defecto cuando el tipo no está en el mapa. */
const DEFAULT_COLOR = "#6B7280"; // gris neutro

/**
 * Devuelve el color hex asociado a un tipo de work item.
 * @param workItemType - valor de `work_item_type` (tolerante a mayúsculas y nulos).
 */
export function getWorkItemTypeColor(workItemType: string | null | undefined): string {
  if (!workItemType) return DEFAULT_COLOR;
  return WORK_ITEM_TYPE_COLORS[workItemType.trim().toLowerCase()] ?? DEFAULT_COLOR;
}

/**
 * Tipos de work item que Stacky trata como INCIDENCIA. Mismo conjunto que usaba
 * `canResolveWithAgent` (plan 166 F5): el tracker publica las incidencias como
 * "Issue" (o "Bug"), no existe un tipo literal "Incidencia" en ADO.
 */
const INCIDENT_TYPES = new Set(["issue", "bug"]);

/** Ícono del distintivo de incidencia (el color NUNCA va solo — a11y). */
export const INCIDENT_ICON = "🚑";

/**
 * ¿Este work item es una incidencia? Fuente única de verdad para el resaltado
 * visual del board y para la disponibilidad del Dev Resolutor.
 */
export function isIncidentWorkItemType(workItemType: string | null | undefined): boolean {
  if (!workItemType) return false;
  return INCIDENT_TYPES.has(workItemType.trim().toLowerCase());
}

/**
 * Etiqueta a mostrar en el badge de tipo. Las incidencias se prefijan con el
 * ícono para que el distintivo no dependa solo del color (daltonismo, temas de
 * alto contraste, capturas en blanco y negro).
 *
 * Plan 277 — se consulta WORK_ITEM_TYPE_LABELS ANTES de devolver el crudo, para
 * que el operador lea "Análisis Técnico" y no el token `tecnico`. El prefijo de
 * incidencia se conserva: sigue aplicándose sobre el rótulo que corresponda.
 */
export function formatWorkItemTypeLabel(workItemType: string | null | undefined): string {
  const raw = (workItemType ?? "").trim();
  if (!raw) return "";
  const label = WORK_ITEM_TYPE_LABELS[raw.toLowerCase()] ?? raw;
  return isIncidentWorkItemType(raw) ? `${INCIDENT_ICON} ${label}` : label;
}

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

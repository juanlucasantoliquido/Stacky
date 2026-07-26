// Plan 213 F5 — Lógica pura del panel de supuestos.
//
// El panel existe para que el operador vea qué asumió el analista y pueda
// confirmarlo o corregirlo. Dos reglas de presentación que no son cosméticas:
// los de impacto alto van primero (son los que pueden invalidar el análisis),
// y un supuesto SIN base declarada se marca como advertencia — es la señal de
// que el agente pudo estar inventando.

export type AssumptionStatus = "pending" | "confirmed" | "corrected";
export type AssumptionImpact = "high" | "medium" | "low";

export interface AssumptionDTO {
  text: string;
  basis?: string;
  impact: AssumptionImpact;
  needs_confirmation?: boolean;
  status?: AssumptionStatus;
  correction?: string;
}

export interface AssumptionsMetaDTO {
  items?: AssumptionDTO[];
  pending?: { text: string; needs?: string }[];
  total?: number;
  unbased_count?: number;
  overload?: boolean;
  marks_ok?: boolean;
  blocked_without_pending?: boolean;
}

const ORDEN: AssumptionImpact[] = ["high", "medium", "low"];

export function readAssumptions(
  metadata: Record<string, unknown> | null | undefined
): AssumptionsMetaDTO | null {
  const bloque = metadata?.assumptions;
  if (!bloque || typeof bloque !== "object" || Array.isArray(bloque)) return null;
  return bloque as AssumptionsMetaDTO;
}

export function groupByImpact(items: AssumptionDTO[] | null | undefined): {
  high: AssumptionDTO[];
  medium: AssumptionDTO[];
  low: AssumptionDTO[];
} {
  const salida = { high: [] as AssumptionDTO[], medium: [] as AssumptionDTO[], low: [] as AssumptionDTO[] };
  for (const item of items ?? []) {
    const impacto: AssumptionImpact = ORDEN.includes(item.impact) ? item.impact : "medium";
    salida[impacto].push(item);
  }
  return salida;
}

/** Cuántos de alto impacto siguen sin decidir: es la cuenta que importa. */
export function pendingHighCount(items: AssumptionDTO[] | null | undefined): number {
  return (items ?? []).filter(
    (i) => i.impact === "high" && (i.status ?? "pending") === "pending"
  ).length;
}

export function badgeLabel(meta: AssumptionsMetaDTO | null | undefined): string {
  const total = meta?.total ?? meta?.items?.length ?? 0;
  if (!total) return "";
  const sinConfirmar = pendingHighCount(meta?.items);
  const plural = total === 1 ? "supuesto" : "supuestos";
  return sinConfirmar > 0
    ? `${total} ${plural} · ${sinConfirmar} sin confirmar`
    : `${total} ${plural}`;
}

/** Un supuesto sin base es la señal de que el agente pudo estar inventando. */
export function isUnbased(item: AssumptionDTO): boolean {
  return !((item.basis ?? "").trim());
}

/** Índices reales dentro de `items`: el PATCH del backend indexa por posición,
 *  y agrupar por impacto reordena la vista. Sin esto se confirmaría otro ítem. */
export function withIndices(
  items: AssumptionDTO[] | null | undefined
): { item: AssumptionDTO; index: number }[] {
  return (items ?? []).map((item, index) => ({ item, index }));
}

export function orderedForDisplay(
  items: AssumptionDTO[] | null | undefined
): { item: AssumptionDTO; index: number }[] {
  const conIndice = withIndices(items);
  const peso = (i: AssumptionDTO) => ORDEN.indexOf(ORDEN.includes(i.impact) ? i.impact : "medium");
  return [...conIndice].sort((a, b) => peso(a.item) - peso(b.item));
}

export function overloadWarning(meta: AssumptionsMetaDTO | null | undefined): string | null {
  return meta?.overload
    ? "Análisis mayormente supuesto — revisá antes de avanzar."
    : null;
}

export function statusLabel(status: AssumptionStatus | undefined): string {
  if (status === "confirmed") return "Confirmado";
  if (status === "corrected") return "Corregido";
  return "Sin confirmar";
}

/** Nada que mostrar ⇒ el panel no se renderiza. Cero ruido cuando no hubo supuestos. */
export function hasSomethingToShow(meta: AssumptionsMetaDTO | null | undefined): boolean {
  return Boolean((meta?.items?.length ?? 0) > 0 || (meta?.pending?.length ?? 0) > 0);
}

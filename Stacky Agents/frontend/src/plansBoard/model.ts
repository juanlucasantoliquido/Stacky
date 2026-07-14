// Plan 128 — Tablero de evolución de planes: tipos + lógica pura (sin React).
export type EstadoPlan =
  | "PROPUESTO"
  | "CRITICADO"
  | "IMPLEMENTADO"
  | "IMPLEMENTADO_PARCIAL"
  | "APROBADO"
  | "SIN_ESTADO";

export interface SuggestedAction {
  kind: string;
  label: string;
  command: string | null;
  natural_language: string;
}

export interface PlanCardDto {
  number: number;
  number_str: string;
  slug: string;
  filename: string;
  path_rel: string;
  title: string;
  estado: string;
  estado_raw: string | null;
  estado_efectivo: EstadoPlan;
  veredicto: string | null;
  version: string | null;
  fecha: string | null;
  duplicate: boolean;
  ledger: { veredicto: string; fecha: string | null; doc_drift: boolean | null } | null;
  unpushed: boolean | null;
  suggested_action: SuggestedAction;
}

export interface BoardDto {
  ok: boolean;
  generated_at: string;
  docs_dir_found: boolean;
  git_available: boolean;
  next_free_number: number;
  totals: Record<string, number>;
  plans: PlanCardDto[];
}

export const ESTADO_CHIP: Record<EstadoPlan, { label: string; color: string }> = {
  PROPUESTO: { label: "Propuesto", color: "#8b5cf6" },
  CRITICADO: { label: "Criticado", color: "#f59e0b" },
  IMPLEMENTADO: { label: "Implementado", color: "#3b82f6" },
  IMPLEMENTADO_PARCIAL: { label: "Impl. parcial", color: "#f97316" },
  APROBADO: { label: "Aprobado", color: "#22c55e" },
  SIN_ESTADO: { label: "Sin estado", color: "#6b7280" },
};

export interface BoardFilters {
  texto: string;
  estado: EstadoPlan | "TODOS";
  soloPendientesPush: boolean;
  soloSinSupervisar: boolean;
}

export function estadoChip(card: PlanCardDto): { label: string; color: string } {
  return ESTADO_CHIP[card.estado_efectivo] ?? ESTADO_CHIP.SIN_ESTADO;
}

export function sinSupervisar(card: PlanCardDto): boolean {
  return card.estado_efectivo === "IMPLEMENTADO" || card.estado_efectivo === "IMPLEMENTADO_PARCIAL";
}

export function filterPlans(plans: PlanCardDto[], f: BoardFilters): PlanCardDto[] {
  const texto = f.texto.trim().toLowerCase();
  return plans.filter((card) => {
    if (texto) {
      const haystack = `${card.number_str} ${card.title} ${card.slug}`.toLowerCase();
      if (!haystack.includes(texto)) return false;
    }
    if (f.estado !== "TODOS" && card.estado_efectivo !== f.estado) return false;
    if (f.soloPendientesPush && card.unpushed !== true) return false;
    if (f.soloSinSupervisar && !sinSupervisar(card)) return false;
    return true;
  });
}

export function buildCopyPayload(a: SuggestedAction): string {
  return a.command ?? a.natural_language;
}

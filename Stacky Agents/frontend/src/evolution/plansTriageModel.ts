// Plan 237 — Triage de planes: tipos + lógica pura (sin React).
export type TriageBucket =
  | "SIN_IMPLEMENTAR" | "SIN_CRITICAR" | "SIN_DOCUMENTO" | "SIN_SUPERVISAR" | "COMPLETADO";

export const BUCKET_ORDER: TriageBucket[] = [
  "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR", "COMPLETADO",
];

// Buckets que arrancan ABIERTOS. COMPLETADO arranca cerrado: es el más numeroso
// y el menos accionable (mata el ruido sin esconder nada).
export const BUCKETS_ABIERTOS_POR_DEFECTO: TriageBucket[] = [
  "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR",
];

// `tone` es un NOMBRE DE CLASE del .module.css. Cero colores literales acá (G6).
export const BUCKET_META: Record<TriageBucket, { label: string; hint: string; tone: string }> = {
  SIN_IMPLEMENTAR: { label: "Sin implementar", hint: "Ya pasaron el juez (o quedaron a medias): toca construirlos.", tone: "toneUrgent" },
  SIN_CRITICAR:    { label: "Sin criticar",    hint: "Escritos, pero todavía sin juez adversarial.",               tone: "toneWarn" },
  SIN_DOCUMENTO:   { label: "Sin documento",   hint: "Comprometidos en un roadmap; falta escribir el .md.",        tone: "toneInfo" },
  SIN_SUPERVISAR:  { label: "Sin supervisar",  hint: "Construidos; falta el cierre del supervisor.",               tone: "tonePending" },
  COMPLETADO:      { label: "Completado",      hint: "Implementados, supervisados y aprobados.",                   tone: "toneDone" },
};

export interface PlanTriageCard {
  number: number; number_str: string; title: string; slug: string;
  filename: string | null; estado: string; estado_efectivo: string;
  triage_bucket: TriageBucket; version: string | null; fecha: string | null;
  duplicate: boolean; unpushed: boolean | null;
  ledger: { veredicto: string; fecha: string | null; doc_drift: boolean | null } | null;
  suggested_action: { kind: string; label: string; command: string | null; natural_language: string };
}

export interface NumberingDto {
  max_number: number; next_free_number: number; next_free_number_raw: number;
  reserved_count: number; duplicates: { number: number; filenames: string[] }[];
}

export interface PlansTriageDto {
  ok: boolean; docs_dir_found: boolean; git_available: boolean;
  next_free_number: number; next_free_number_raw?: number; reserved_count?: number;
  triage_order: string[]; triage_totals: Record<string, number>;
  totals: Record<string, number>;
  census: { files_seen: number; plans_parsed: number; skipped_not_a_plan: number;
            skipped_oversize: number; skipped_unreadable: number; skipped_over_cap: number;
            skipped_subdirs: number; subdir_examples: string[] };
  numbering?: NumberingDto;
  plans: PlanTriageCard[];
}

export function bucketRank(b: string): number {
  const i = BUCKET_ORDER.indexOf(b as TriageBucket);
  return i === -1 ? BUCKET_ORDER.length : i;   // desconocido al final, nunca oculto
}

/** Agrupa respetando BUCKET_ORDER. Devuelve TODOS los grupos, incluso vacíos. */
export function groupByBucket(plans: PlanTriageCard[]): { bucket: TriageBucket; cards: PlanTriageCard[] }[] {
  return BUCKET_ORDER.map((bucket) => ({
    bucket,
    cards: plans.filter((p) => p.triage_bucket === bucket)
                .slice()
                .sort((a, b) => b.number - a.number),
  }));
}

/** Filtro de texto: número, título o slug. Vacío = todo. */
export function filterByText(plans: PlanTriageCard[], texto: string): PlanTriageCard[] {
  const q = texto.trim().toLowerCase();
  if (!q) return plans;
  return plans.filter((p) => `${p.number_str} ${p.title} ${p.slug}`.toLowerCase().includes(q));
}

/** Frase del censo. Devuelve null si no se excluyó nada (nada que declarar). */
export function censusSummary(c: PlansTriageDto["census"]): string | null {
  const fuera = c.skipped_subdirs + c.skipped_oversize + c.skipped_unreadable + c.skipped_over_cap;
  if (fuera === 0) return null;
  const partes: string[] = [];
  if (c.skipped_subdirs) partes.push(`${c.skipped_subdirs} archivados en subcarpetas`);
  if (c.skipped_oversize) partes.push(`${c.skipped_oversize} demasiado grandes`);
  if (c.skipped_unreadable) partes.push(`${c.skipped_unreadable} ilegibles`);
  if (c.skipped_over_cap) partes.push(`${c.skipped_over_cap} más allá del tope de lectura`);
  return `${c.plans_parsed} planes leídos · fuera del listado: ${partes.join(", ")}.`;
}

/** [ADICIÓN] Aviso de colisión de numeración. null si no hay duplicados. */
export function numberingAlert(n: NumberingDto | undefined): string | null {
  if (!n || !n.duplicates.length) return null;
  const lista = n.duplicates
    .map((d) => `${d.number} (${d.filenames.join(", ")})`)
    .join(" · ");
  return `Números de plan duplicados: ${lista}. Renumerá uno antes de seguir.`;
}

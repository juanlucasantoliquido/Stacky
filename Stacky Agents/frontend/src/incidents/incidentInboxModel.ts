/**
 * Plan 238 F4 — Modelo PURO de la bandeja de incidencias.
 * Sin React, sin DOM, sin fetch: testeable con vitest en entorno node
 * (el repo no tiene @testing-library/react ni jsdom instalados).
 */

export type IncidentScope = "open" | "all";

export interface IncidentInboxItem {
  id: number;
  ado_id: number;
  title: string;
  work_item_type?: string;
  ado_state?: string;
  ado_url?: string;
  assigned_to_ado?: string | null;
  stacky_status?: string;
  last_synced_at?: string;
  is_open: boolean;
}

export interface IncidentInboxCounts {
  open: number;
  closed: number;
  total: number;
}

export interface IncidentInboxResponse {
  ok: boolean;
  scope: IncidentScope;
  counts: IncidentInboxCounts;
  truncated: boolean;
  /** Plan 238 4.1.4 — tickets del proyecto SIN work_item_type sincronizado. */
  untyped_count: number;
  /** Tracker del proyecto activo ("ado" | "gitlab" | null). Solo informativo. */
  provider: string | null;
  incident_types: string[];
  closed_states: string[];
  items: IncidentInboxItem[];
}

export interface IncidentInboxStatus {
  ok: boolean;
  enabled: boolean;
  incident_types: string[];
  incident_types_source: string;
  closed_states: string[];
  closed_states_source: string;
}

/** "all"/"todas" -> "all"; cualquier otra cosa -> "open". Espejo de
 *  normalize_scope() en backend/services/incident_inbox.py. */
export function parseScope(raw: string | null | undefined): IncidentScope {
  const norm = (raw ?? "").trim().toLowerCase();
  return norm === "all" || norm === "todas" ? "all" : "open";
}

/** Desempate ESTABLE que replica el orden del servidor (abiertas primero,
 *  last_synced_at desc, ado_id desc). PURA: devuelve un array nuevo. */
export function sortIncidents(items: IncidentInboxItem[]): IncidentInboxItem[] {
  return items.slice().sort((a, b) => {
    if (a.is_open !== b.is_open) return a.is_open ? -1 : 1;
    const ta = a.last_synced_at ?? "";
    const tb = b.last_synced_at ?? "";
    if (ta !== tb) return tb.localeCompare(ta);
    return b.ado_id - a.ado_id;
  });
}

/** Busqueda case-insensitive sobre titulo, ado_id y estado. Texto vacio => todo. */
export function filterBySearch(
  items: IncidentInboxItem[],
  search: string
): IncidentInboxItem[] {
  const q = search.trim().toLowerCase();
  if (!q) return items.slice();
  return items.filter(
    (i) =>
      i.title.toLowerCase().includes(q) ||
      String(i.ado_id).includes(q) ||
      (i.ado_state ?? "").toLowerCase().includes(q)
  );
}

/** Conteo por estado del tracker, ordenado por cantidad desc y luego alfabetico.
 *  Estado vacio se reporta como "(sin estado)". */
export function countByState(
  items: IncidentInboxItem[]
): { state: string; count: number }[] {
  const map = new Map<string, number>();
  for (const i of items) {
    const key = (i.ado_state ?? "").trim() || "(sin estado)";
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([state, count]) => ({ state, count }))
    .sort((a, b) => (b.count - a.count) || a.state.localeCompare(b.state));
}

/** Texto para el portapapeles (se copia con copyText de services/copyService.ts).
 *  Una linea por incidencia: "#<ado_id>\t<estado>\t<titulo>\t<url>". */
export function formatIncidentsForCopy(items: IncidentInboxItem[]): string {
  return items
    .map((i) =>
      [`#${i.ado_id}`, i.ado_state ?? "", i.title, i.ado_url ?? ""].join("\t")
    )
    .join("\n");
}

/** Resumen para la cabecera: "7 abiertas de 19". */
export function summaryLabel(counts: IncidentInboxCounts): string {
  return `${counts.open} abierta${counts.open === 1 ? "" : "s"} de ${counts.total}`;
}

/** Plan 238 4.1.4 — ¿la lista está vacía porque el tracker no sincroniza el
 *  tipo de ítem? Decide entre "no hay incidencias" y el mensaje explicativo. */
export function isProviderBlind(res: IncidentInboxResponse | null | undefined): boolean {
  if (!res) return false;
  return res.items.length === 0 && res.counts.total === 0 && (res.untyped_count ?? 0) > 0;
}

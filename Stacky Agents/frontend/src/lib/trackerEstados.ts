/** Plan 282 F6 — vocabulario de ESTADOS por tracker. Lógica pura, sin React.
 *
 *  Fricción FUNCIONAL, no cosmética: `CLOSED_STATES` era una lista de estados
 *  ADO (`Done`/`Closed`/`Resolved`/`Removed`/`Completed`) y `ADO_STATE_COLORS`
 *  sólo conocía estados ADO. En GitLab, cuyos estados son `opened`/`closed`, el
 *  filtro "Solo abiertos" no filtraba NADA y todos los badges caían al mismo
 *  gris. */

import { estadosRuteadosActivos } from "../services/trackerUiFlags";

const CERRADOS_ADO = ["Done", "Closed", "Resolved", "Removed", "Completed"];

/** GitLab: el estado nativo `closed`, más las dos claves lógicas que
 *  `_state_map_for_gitlab` (backend/services/gitlab_provider.py) marca con
 *  `closed: true` — se materializan como etiquetas `stacky::accepted` y
 *  `stacky::rejected`. */
const CERRADOS_GITLAB = [
  "closed", "stacky::accepted", "stacky::rejected", "accepted", "rejected",
];

const CERRADOS_POR_TRACKER: Record<string, string[]> = {
  azure_devops: CERRADOS_ADO,
  gitlab: CERRADOS_GITLAB,
  // Jira y Mantis siguen usando el vocabulario ADO heredado: sus caminos de
  // cierre no se tocaron todavía y degradar a lista vacía apagaría el filtro
  // en pantallas que hoy funcionan.
  jira: CERRADOS_ADO,
  mantis: CERRADOS_ADO,
};

const COLOR_NEUTRO = "#6b7280";

const COLORES_ADO: Record<string, string> = {
  "Active":      "#3b82f6",
  "In Progress": "#3b82f6",
  "En Progreso": "#3b82f6",
  "Resolved":    "#a855f7",
  "Committed":   "#f59e0b",
  "New":         "#6b7280",
  "Done":        "#22c55e",
  "Closed":      "#22c55e",
};

const COLORES_GITLAB: Record<string, string> = {
  "opened":              "#3b82f6",
  "closed":              "#22c55e",
  "stacky::in_progress": "#3b82f6",
  "in_progress":         "#3b82f6",
  "stacky::functional":  "#a855f7",
  "functional":          "#a855f7",
  "stacky::accepted":    "#22c55e",
  "accepted":            "#22c55e",
  "stacky::rejected":    "#ef4444",
  "rejected":            "#ef4444",
};

function estadosCerrados(tracker: string | null | undefined): string[] {
  // Plan 282 F8 — kill-switch STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED: con OFF
  // vuelve el vocabulario unico de ADO (el comportamiento previo al plan).
  if (!estadosRuteadosActivos()) return CERRADOS_ADO;
  return CERRADOS_POR_TRACKER[(tracker ?? "").trim().toLowerCase()] ?? CERRADOS_ADO;
}

/** La LISTA de estados terminales del tracker.
 *
 *  Existe porque `canResolveWithAgent` (incidents/devResolverModel.ts) espera
 *  una **lista**, no un predicado: su contrato no se cambia desde acá. */
export function sugerenciasDeEstadoCerrado(tracker: string | null | undefined): string[] {
  return [...estadosCerrados(tracker)];
}

/** True si el estado es terminal EN ESE TRACKER. Comparación CASE-INSENSITIVE:
 *  GitLab devuelve minúsculas y la UI enseñaba vocabulario ADO. */
export function esEstadoCerrado(
  estado: string | null | undefined,
  tracker: string | null | undefined,
): boolean {
  const e = (estado ?? "").trim().toLowerCase();
  if (!e) return false;
  return estadosCerrados(tracker).some((c) => c.toLowerCase() === e);
}

/** Color del badge por estado y tracker. NUNCA devuelve undefined. */
export function colorDeEstado(
  estado: string | null | undefined,
  tracker: string | null | undefined,
): string {
  const crudo = (estado ?? "").trim();
  if (!crudo) return COLOR_NEUTRO;
  const tipo = estadosRuteadosActivos() ? (tracker ?? "").trim().toLowerCase() : "azure_devops";
  const tabla = tipo === "gitlab" ? COLORES_GITLAB : COLORES_ADO;
  if (tabla[crudo]) return tabla[crudo];
  const enMinusculas = crudo.toLowerCase();
  for (const [clave, color] of Object.entries(tabla)) {
    if (clave.toLowerCase() === enMinusculas) return color;
  }
  // Último recurso: un estado desconocido que igual CIERRA se pinta de cerrado,
  // en vez de caer al gris junto con los abiertos.
  return esEstadoCerrado(crudo, tracker) ? "#22c55e" : COLOR_NEUTRO;
}

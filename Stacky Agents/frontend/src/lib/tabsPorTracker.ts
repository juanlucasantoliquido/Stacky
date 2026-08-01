/** Plan 282 F7 — qué tabs tienen sentido en cada tracker. Lógica pura, sin React.
 *
 *  Hoy PM, Sprint Board y User Stats se ofrecen en el menú de un proyecto GitLab
 *  y, al abrirlos, el backend responde "solo está disponible para proyectos
 *  Azure DevOps". Es un callejón sin salida ofrecido en el menú. */

/** Tabs que HOY sólo funcionan con Azure DevOps.
 *
 *  La lista NO se inventa: se deriva del guard del backend
 *  `tracker.get("type", "azure_devops") != "azure_devops"`, que en
 *  `backend/api/pm.py` aparece DIEZ veces y devuelve TRACKER_NOT_SUPPORTED por
 *  el helper de respuesta. El blueprint entero es ADO-only; los 3 tabs del
 *  frontend que consumen ESE blueprint son estos. */
export const TABS_SOLO_ADO = ["pm", "sprint", "userstats"] as const;

import { gateDeTabsActivo } from "../services/trackerUiFlags";

const NOMBRE_HUMANO: Record<string, string> = {
  pm: "El Command Center de PM",
  sprint: "El Sprint Board",
  userstats: "Las estadísticas por usuario",
};

function nombreDelTracker(tracker: string | null | undefined): string {
  const t = (tracker ?? "").trim().toLowerCase();
  if (t === "gitlab") return "GitLab";
  if (t === "jira") return "Jira";
  if (t === "mantis") return "Mantis";
  return "este tracker";
}

/** True si el tab debe ofrecerse (habilitado) para ese tracker.
 *
 *  Sin proyecto (`null`/`undefined`) falla ABIERTO: no se esconde ni deshabilita
 *  nada mientras el proyecto todavía no cargó. Los gates de tab que nacen
 *  `false` matan el deep link — es un defecto conocido de este repo. */
export function tabDisponible(tab: string, tracker: string | null | undefined): boolean {
  // Plan 282 F8 — kill-switch STACKY_ADO_ONLY_TABS_GATED_ENABLED: con OFF, nada
  // se deshabilita por tracker (comportamiento previo al plan).
  if (!gateDeTabsActivo()) return true;
  if (!(TABS_SOLO_ADO as readonly string[]).includes(tab)) return true;
  const t = (tracker ?? "").trim().toLowerCase();
  if (!t) return true;                       // falla abierto
  return t === "azure_devops";
}

/** Motivo legible para el tooltip cuando NO está disponible. Nunca vacío. */
export function motivoNoDisponible(tab: string, tracker: string | null | undefined): string {
  const quien = NOMBRE_HUMANO[tab] ?? "Esta sección";
  if (tabDisponible(tab, tracker)) return "";
  return `${quien} requiere Azure DevOps; este proyecto usa ${nombreDelTracker(tracker)}.`;
}

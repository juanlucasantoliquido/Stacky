/** Plan 276 F7 + Plan 282 F4 — rótulos de la app según el tracker del proyecto.
 *
 *  Antes decían "ADO" siempre: en un proyecto GitLab el operador leía instrucciones
 *  para sincronizar, publicar y abrir un tracker que su proyecto no usa, mientras el
 *  título de la propia página ya decía "Tickets GitLab".
 *
 *  Lógica pura, sin React: RTL/jsdom no están instalados en este repo, así que todo
 *  lo testeable vive acá y los componentes solo pintan. */

import { rotulosRuteadosActivos } from "../services/trackerUiFlags";

export type TrackerType = "azure_devops" | "gitlab" | "jira" | "mantis";

const NOMBRES: Record<TrackerType, string> = {
  azure_devops: "ADO",
  gitlab: "GitLab",
  jira: "Jira",
  mantis: "Mantis",
};

/** Nombre COMPLETO, para textos donde la sigla queda pobre ("Abrir en …"). */
const NOMBRES_LARGOS: Record<TrackerType, string> = {
  azure_devops: "Azure DevOps",
  gitlab: "GitLab",
  jira: "Jira",
  mantis: "Mantis",
};

/** Prefijo de referencia de un item POR TRACKER. ADO usa "ADO-123"; GitLab usa
 *  "#123", que es la notación que el propio GitLab muestra. */
const PREFIJOS_DE_REF: Record<TrackerType, string> = {
  azure_devops: "ADO-",
  gitlab: "#",
  jira: "Jira-",
  mantis: "Mantis-",
};

/** Sugerencias de estado de cierre POR TRACKER.
 *  ADO: las 4 opciones reales del `<datalist>` de FinishWorkButton.
 *  GitLab: las 4 claves lógicas REALES de `_state_map_for_gitlab`
 *  (backend/services/gitlab_provider.py). Nunca se sugieren estados que el
 *  tracker del operador no tiene: sugerir "Done" en GitLab es la receta del
 *  `transition_failed` que el plan 271 dejó documentado. */
const ESTADOS_FINALES: Record<TrackerType, string[]> = {
  azure_devops: ["Done", "Closed", "Resolved", "Active"],
  gitlab: ["functional", "accepted", "rejected", "in_progress"],
  jira: [],
  mantis: [],
};

function clave(tipo: string | undefined | null): TrackerType | null {
  // Plan 282 F8 — kill-switch STACKY_TRACKER_LABELS_GLOBAL_ENABLED. Con OFF, el
  // resolutor UNICO que usan todos los helpers responde siempre Azure DevOps:
  // la app vuelve, byte a byte, a los rotulos previos al plan.
  if (!rotulosRuteadosActivos()) return "azure_devops";
  const k = (tipo ?? "") as TrackerType;
  return k in NOMBRES ? k : null;
}

/** Nombre visible del tracker. Un tipo desconocido cae a "Tracker", nunca a "ADO". */
export function nombreDeTracker(tipo: string | undefined | null): string {
  const k = clave(tipo);
  return k ? NOMBRES[k] : "Tracker";
}

/** Nombre completo. Desconocido → "el tracker" (encaja en "Abrir en el tracker"). */
export function nombreLargoDeTracker(tipo: string | undefined | null): string {
  const k = clave(tipo);
  return k ? NOMBRES_LARGOS[k] : "el tracker";
}

export function tituloDeTickets(tipo: string | undefined | null): string {
  const k = clave(tipo);
  // Sin proyecto activo el rótulo queda NEUTRO ("Tickets"), no "Tickets Tracker":
  // el sidebar y la paleta se pintan antes de que haya proyecto.
  return k ? `Tickets ${NOMBRES[k]}` : "Tickets";
}

export function accionSincronizar(tipo: string | undefined | null): string {
  return `Sincronizar ${nombreDeTracker(tipo)}`;
}

/** El tracker EFECTIVO de un ticket: el suyo si lo trae, si no el del proyecto.
 *
 *  `Ticket.tracker_type` es **opcional** en el payload: con la flag de
 *  vocabulario canónico apagada el backend devuelve las 16 claves legacy y ese
 *  campo NO viene. Sin este fallback, un proyecto Azure DevOps pasaría a rotular
 *  "Tracker-1234" en todas sus tarjetas — una regresión visible para el caso que
 *  hoy funciona. */
export function trackerEfectivo(
  delTicket: string | null | undefined,
  delProyecto: string | null | undefined,
): string | null {
  const propio = (delTicket ?? "").trim();
  if (propio) return propio;
  const proyecto = (delProyecto ?? "").trim();
  return proyecto || null;
}

/** Referencia visible de un item: "ADO-1234" | "#1115" | "Tracker-9". */
export function refDeTicket(
  tipo: string | undefined | null,
  id: number | string | null | undefined,
): string {
  const k = clave(tipo);
  const prefijo = k ? PREFIJOS_DE_REF[k] : `${nombreDeTracker(tipo)}-`;
  return `${prefijo}${id ?? "?"}`;
}

/** "Abrir en Azure DevOps ↗" | "Abrir en GitLab ↗" | "Abrir en el tracker ↗" */
export function accionAbrirEn(tipo: string | undefined | null): string {
  return `Abrir en ${nombreLargoDeTracker(tipo)} ↗`;
}

/** "Publicar comentario en ADO" | "Publicar comentario en GitLab" */
export function accionPublicarComentario(tipo: string | undefined | null): string {
  return `Publicar comentario en ${nombreDeTracker(tipo)}`;
}

/** "Estado destino en ADO" | "Estado destino en GitLab" */
export function etiquetaEstadoDestino(tipo: string | undefined | null): string {
  return `Estado destino en ${nombreDeTracker(tipo)}`;
}

/** "Estado ADO" | "Estado GitLab" — la columna/campo del estado del tracker. */
export function etiquetaEstadoDeTicket(tipo: string | undefined | null): string {
  return `Estado ${nombreDeTracker(tipo)}`;
}

/** Sugerencias de estado final del tracker. Nunca devuelve estados ajenos. */
export function sugerenciasDeEstadoFinal(tipo: string | undefined | null): string[] {
  const k = clave(tipo);
  return k ? [...ESTADOS_FINALES[k]] : [];
}

/** [ADICIÓN ARQUITECTO A3] Rótulo del tab, ruteado por tracker, SIN tocar TAB_META.
 *
 *  Por qué existe: `TAB_META` (components/shell/shellNav.ts) es un
 *  `Record<ShellTab, ShellTabMeta>` congelado por CUATRO suites
 *  (shellNav.test.ts por `Object.keys` y por `.label`/`.iconName`,
 *  shellIcons.test.ts y shellIconsCoverage.test.ts) y consumido por App.tsx como
 *  `TAB_META[t]?.label`. Convertirlo en función rompe las cuatro.
 *
 *  Contrato: para "tickets" devuelve `tituloDeTickets(tracker)`; para cualquier
 *  otro tab devuelve el label estático que recibe, sin tocarlo. Función pura: no
 *  lee `TAB_META` por su cuenta ni importa nada del shell. */
export function labelDeTab(
  tab: string,
  labelEstatico: string,
  tracker: string | null | undefined,
): string {
  return tab === "tickets" ? tituloDeTickets(tracker) : labelEstatico;
}

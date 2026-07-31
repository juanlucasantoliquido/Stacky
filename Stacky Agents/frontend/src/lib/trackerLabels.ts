/** Plan 276 F7 — rótulos de la pantalla de tickets según el tracker del proyecto
 *  activo. Antes decían "ADO" siempre: en un proyecto GitLab el operador leía una
 *  instrucción para sincronizar con un tracker que su proyecto no usa.
 *
 *  Lógica pura, sin React: RTL/jsdom no están instalados en este repo, así que todo
 *  lo testeable vive acá y los componentes solo pintan. */

export type TrackerType = "azure_devops" | "gitlab" | "jira" | "mantis";

const NOMBRES: Record<TrackerType, string> = {
  azure_devops: "ADO",
  gitlab: "GitLab",
  jira: "Jira",
  mantis: "Mantis",
};

/** Nombre visible del tracker. Un tipo desconocido cae a "Tracker", nunca a "ADO". */
export function nombreDeTracker(tipo: string | undefined | null): string {
  return NOMBRES[(tipo ?? "") as TrackerType] ?? "Tracker";
}

export function tituloDeTickets(tipo: string | undefined | null): string {
  return `Tickets ${nombreDeTracker(tipo)}`;
}

export function accionSincronizar(tipo: string | undefined | null): string {
  return `Sincronizar ${nombreDeTracker(tipo)}`;
}

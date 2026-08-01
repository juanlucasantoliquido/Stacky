/** Plan 282 F8 — kill-switches de UI del eje "GitLab deja de ser un ADO
 *  disfrazado". Módulo PURO con estado de módulo, mismo patrón que
 *  `services/shortcuts.ts` (`setUiShortcutsEnabled`/`isUiShortcutsEnabled`).
 *
 *  Por qué estado de módulo y no props: los helpers que gatean son funciones
 *  PURAS consumidas desde ~30 sitios, incluidos módulos de datos sin contexto
 *  React. Pasar 4 booleanos por props a través de todos sería peor.
 *
 *  TODOS nacen en `true`: si el backend no responde, la app se comporta como el
 *  plan la dejó. El operador los apaga desde Configuración → Arnés y el
 *  comportamiento vuelve al previo, sin recompilar.
 *
 *  Cada uno tiene un efecto REAL y verificable (no son placebos):
 *   - LABELS  OFF → todos los rótulos vuelven a hablar Azure DevOps.
 *   - URLS    OFF → la app deja de componer URLs de tracker del lado del
 *                   cliente y usa SÓLO la que manda el backend.
 *   - ESTADOS OFF → el vocabulario de estados vuelve a ser el de ADO.
 *   - TABS    OFF → ningún tab se deshabilita por tracker.
 */

export interface TrackerUiFlags {
  labelsGlobal: boolean;
  urlsRouted: boolean;
  stateFilterRouted: boolean;
  adoOnlyTabsGated: boolean;
}

/** Las CLAVES exactas del registro del arnés. Se leen desde App.tsx. */
export const CLAVES_DE_FLAG = {
  labelsGlobal: "STACKY_TRACKER_LABELS_GLOBAL_ENABLED",
  urlsRouted: "STACKY_TRACKER_URLS_ROUTED_ENABLED",
  stateFilterRouted: "STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED",
  adoOnlyTabsGated: "STACKY_ADO_ONLY_TABS_GATED_ENABLED",
} as const;

const estado: TrackerUiFlags = {
  labelsGlobal: true,
  urlsRouted: true,
  stateFilterRouted: true,
  adoOnlyTabsGated: true,
};

/** Aplica lo que devolvió `/api/harness-flags`. Una clave ausente NO apaga nada. */
export function setTrackerUiFlags(parcial: Partial<TrackerUiFlags>): void {
  for (const clave of Object.keys(estado) as (keyof TrackerUiFlags)[]) {
    const v = parcial[clave];
    if (typeof v === "boolean") estado[clave] = v;
  }
}

export function trackerUiFlags(): TrackerUiFlags {
  return { ...estado };
}

export function rotulosRuteadosActivos(): boolean { return estado.labelsGlobal; }
export function urlsRuteadasActivas(): boolean { return estado.urlsRouted; }
export function estadosRuteadosActivos(): boolean { return estado.stateFilterRouted; }
export function gateDeTabsActivo(): boolean { return estado.adoOnlyTabsGated; }

/** Sólo para tests: restaura los defaults. */
export function resetTrackerUiFlags(): void {
  estado.labelsGlobal = true;
  estado.urlsRouted = true;
  estado.stateFilterRouted = true;
  estado.adoOnlyTabsGated = true;
}

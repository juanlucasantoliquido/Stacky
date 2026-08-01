/**
 * Plan 129 — Paleta global: datos y funciones PURAS de CommandPalette.
 *
 * Centraliza los tipos compartidos (antes vivían sin exportar dentro de
 * CommandPalette.tsx, lo que rompía tsc al no poder reusarlos acá — C3 de la
 * crítica v2 del plan), la navegación total (13 tabs) y el merge de
 * resultados remotos de búsqueda profunda. Testeable sin jsdom.
 *
 * Plan 267 F5 — se agrega el vocabulario "devops-action" y la funcion pura
 * devopsActionCommands(). Edicion ADITIVA: no se reordena CommandKind, ni se
 * modifica NAV_COMMANDS, fuzzyScore o mergeDeepResults.
 *
 * Plan 282 F4 — se agrega buildNavCommands(tracker): el rotulo del tab de
 * tickets sigue al tracker del proyecto activo. NAV_COMMANDS se CONSERVA (es
 * buildNavCommands(null)) para no romper importadores ni su test.
 */
import { tituloDeTickets } from "../lib/trackerLabels";
import {
  IMPACT_TEXT,
  navPathWithParams,
  paletteMode,
} from "../services/devopsActionRunner";
import type { DevOpsActionMeta } from "../services/devopsActionTypes";

export type CommandKind =
  | "ticket"
  | "agent"
  | "pack"
  | "project"
  | "nav"
  | "execution"
  | "doc"
  | "server"
  | "flag"
  // Plan 267 F5 — va AL FINAL a proposito, para no alterar el orden que otros
  // modulos puedan asumir. EntityKind (services/entityActions.ts) usa
  // Extract<CommandKind, "execution" | "ticket">, asi que NO se ve afectado.
  | "devops-action";

export interface Command {
  id: string;
  kind: CommandKind;
  icon: string;
  label: string;
  hint?: string;
  run: () => void;
}

/** Movido desde CommandPalette.tsx (antes local, sin exportar). Comportamiento intacto. */
export function fuzzyScore(query: string, text: string): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (t.includes(q)) return 100 - t.indexOf(q);
  // Cada caracter de q debe aparecer en orden en t
  let qi = 0;
  let lastIdx = -1;
  let gaps = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      if (lastIdx >= 0) gaps += ti - lastIdx - 1;
      lastIdx = ti;
      qi++;
    }
  }
  if (qi < q.length) return 0;
  return Math.max(1, 50 - gaps);
}

interface NavCommandSpec {
  id: string;
  path: string;
  label: string;
  icon: string;
}

/** Una entrada por cada uno de los 13 tabs de App.tsx:30 (TAB_PATHS, App.tsx:32-46).
 *
 *  Plan 282 F4 — el rótulo del tab de tickets NO se hardcodea más: sale de
 *  `tituloDeTickets`, que sin tracker devuelve el neutro "Tickets". La constante
 *  se CONSERVA exportada (la consumen `commandPaletteData.test.ts` y los
 *  importadores existentes) y equivale a `buildNavCommands(null)`; el consumidor
 *  real usa `buildNavCommands(trackerType)`. */
export const NAV_COMMANDS: NavCommandSpec[] = [
  { id: "nav-tickets", path: "/", label: `Ir a ${tituloDeTickets(null)}`, icon: "📋" },
  // Plan 238 — el emoji va literal: NAV_COMMANDS es data pura sin imports de
  // utilidades. Es el mismo valor que INCIDENT_ICON (utils/workItemTypeColor).
  { id: "nav-incidencias", path: "/incidencias", label: "Ir a Incidencias", icon: "🚑" },
  { id: "nav-team", path: "/team", label: "Ir a Mi Equipo", icon: "⚡" },
  { id: "nav-review", path: "/review", label: "Ir a Revisión", icon: "🧭" },
  { id: "nav-unblocker", path: "/unblocker", label: "Ir a Desatascador", icon: "🧹" },
  { id: "nav-pm", path: "/pm", label: "Ir a PM", icon: "📊" },
  { id: "nav-logs", path: "/logs", label: "Ir a System Logs", icon: "🔍" },
  { id: "nav-settings", path: "/settings", label: "Ir a Configuración", icon: "⚙️" },
  { id: "nav-docs", path: "/docs", label: "Ir a Docs", icon: "📄" },
  { id: "nav-memory", path: "/memory", label: "Ir a Memoria", icon: "🧠" },
  { id: "nav-diagnostics", path: "/diagnostics", label: "Ir a Diagnóstico", icon: "🩺" },
  { id: "nav-history", path: "/history", label: "Ir a Historial", icon: "🕘" },
  { id: "nav-migrador", path: "/migrador", label: "Ir a Migrador", icon: "🔀" },
  { id: "nav-devops", path: "/devops", label: "Ir a DevOps", icon: "🛠️" },
];

/** Plan 282 F4 — el catálogo de navegación con el rótulo del tracker activo.
 *
 *  Mismo largo, mismos `path` y mismos `id` que `NAV_COMMANDS` (los `id` son
 *  claves estables que el consumidor filtra por gate): lo único que cambia es el
 *  `label` del tab de tickets. Función pura: no lee ningún store. */
export function buildNavCommands(tracker: string | null | undefined): NavCommandSpec[] {
  return NAV_COMMANDS.map((nc) =>
    nc.id === "nav-tickets" ? { ...nc, label: `Ir a ${tituloDeTickets(tracker)}` } : nc,
  );
}

export interface RemoteHit {
  kind: string;
  id: string;
  label: string;
  hint: string;
  nav: string;
}

export interface RemoteGroup {
  kind: string;
  hits: RemoteHit[];
}

const DEEP_ICONS: Record<string, string> = {
  ticket: "🎫",
  execution: "🏃",
  doc: "📄",
  server: "🖥️",
  flag: "🚩",
  "devops-action": "⚡", // Plan 267 F5
};

/**
 * Plan 267 F5 — Convierte el catalogo de acciones DevOps en Command[].
 *
 * DOBLE CERROJO (§4.10, calcado de entityActions.ts, que ya resolvio esto para
 * 2 entidades): una accion de ESCRITURA nunca queda a un fuzzy-match + Enter de
 * distancia. `paletteMode(a)` decide, y mira `effect` ANTES que `reach`:
 *   - 'run'    => el Command EJECUTA (via onRun). Solo effect 'read'.
 *   - 'nav'    => el Command NAVEGA a navPathWithParams(a, {}) y NO ejecuta.
 *                 El label lo dice: "Ir a <accion>".
 *   - 'hidden' => no entra a la paleta.
 * La paleta jamas confirma sola, y jamas dispara una escritura.
 */
export function devopsActionCommands(
  actions: DevOpsActionMeta[],
  onRun: (a: DevOpsActionMeta) => void,
  onNavigate: (path: string) => void
): Command[] {
  const out: Command[] = [];
  for (const a of actions ?? []) {
    const mode = paletteMode(a);
    if (mode === "hidden") continue;
    if (mode === "run") {
      out.push({
        id: `devops-action-${a.id}`,
        kind: "devops-action",
        icon: "⚡",
        label: a.label,
        hint: a.summary,
        run: () => onRun(a),
      });
      continue;
    }
    out.push({
      id: `devops-action-nav-${a.id}`,
      kind: "devops-action",
      icon: "⚠️",
      label: `Ir a ${a.label}`,
      hint: `Escribe · ${IMPACT_TEXT[a.impact]} · se hace desde el panel`,
      run: () => onNavigate(navPathWithParams(a, {})),
    });
  }
  return out;
}

/**
 * Aplana los grupos remotos de /api/search/global a Command[], descartando
 * hits cuyo `kind-id` ya esté en localIds (dedup: lo local gana). Respeta el
 * orden de `groups` (y de los hits dentro de cada grupo) tal como llega.
 */
export function mergeDeepResults(
  localIds: Set<string>,
  groups: RemoteGroup[],
  onNavigate: (path: string) => void
): Command[] {
  const out: Command[] = [];
  for (const group of groups) {
    for (const hit of group.hits) {
      const key = `${hit.kind}-${hit.id}`;
      if (localIds.has(key)) continue;
      out.push({
        id: key,
        kind: hit.kind as CommandKind,
        icon: DEEP_ICONS[hit.kind] ?? "🔎",
        label: hit.label,
        hint: hit.hint || undefined,
        run: () => onNavigate(hit.nav),
      });
    }
  }
  return out;
}

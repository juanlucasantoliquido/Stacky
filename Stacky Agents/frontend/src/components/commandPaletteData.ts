/**
 * Plan 129 — Paleta global: datos y funciones PURAS de CommandPalette.
 *
 * Centraliza los tipos compartidos (antes vivían sin exportar dentro de
 * CommandPalette.tsx, lo que rompía tsc al no poder reusarlos acá — C3 de la
 * crítica v2 del plan), la navegación total (13 tabs) y el merge de
 * resultados remotos de búsqueda profunda. Testeable sin jsdom.
 */

export type CommandKind =
  | "ticket"
  | "agent"
  | "pack"
  | "project"
  | "nav"
  | "execution"
  | "doc"
  | "server"
  | "flag";

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

/** Una entrada por cada uno de los 13 tabs de App.tsx:30 (TAB_PATHS, App.tsx:32-46). */
export const NAV_COMMANDS: NavCommandSpec[] = [
  { id: "nav-team", path: "/", label: "Ir a Mi Equipo", icon: "⚡" },
  { id: "nav-tickets", path: "/tickets", label: "Ir a Tickets ADO", icon: "📋" },
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
};

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

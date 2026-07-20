// frontend/src/services/routes.ts — Plan 165 F1
// Contrato de URL tipado de Stacky. Router CASERO (NO react-router).
// Parser/serializer PUROS: no tocan window (App.tsx pasa pathname/search).

export type Tab =
  | "team" | "tickets" | "review" | "unblocker" | "pm" | "logs"
  | "settings" | "docs" | "memory" | "diagnostics" | "history"
  | "migrador" | "devops" | "dbcompare" | "costcenter" | "planes" | "evolution";

// MOVIDO desde App.tsx (fuente única). App.tsx pasará a importarlo (F3).
// La vista índice (raíz "/") es TICKETS: al abrir la app se aterriza en el
// tablero de tickets. "team" (Mi Equipo) tiene su propio path "/team" y es una
// vista ocultable (default oculta, ver uiSectionsStore).
export const TAB_PATHS: Record<Tab, string> = {
  tickets: "/", team: "/team", review: "/review", unblocker: "/unblocker",
  pm: "/pm", logs: "/logs", settings: "/settings", docs: "/docs",
  memory: "/memory", diagnostics: "/diagnostics", history: "/history",
  migrador: "/migrador", devops: "/devops", dbcompare: "/dbcompare",
  costcenter: "/costcenter", planes: "/planes", evolution: "/evolution", // Plan 167
};

export interface RouteState {
  tab: Tab;
  subtab?: string;                 // 2do segmento del path (hoy solo Settings lo usa)
  exec?: number;                   // ?exec=<id> — drawer de ejecución (clave canónica)
  query: Record<string, string>;   // TODO otro query param, preservado verbatim
}

// Clave canónica primero; alias legacy segundo (Plan de paleta emitía "execution").
const EXEC_KEYS = ["exec", "execution"] as const;

/** (interno) matchea el 1er segmento contra un tab conocido (nunca "tickets"/raíz). */
function matchKnownTab(segments: string[]): Tab | undefined {
  if (segments.length === 0) return undefined;
  const first = "/" + segments[0];
  const match = (Object.entries(TAB_PATHS) as [Tab, string][])
    .find(([, path]) => path !== "/" && path === first);
  return match?.[0];
}

/** tab desde el primer segmento del path. Vacío o desconocido => "tickets" (índice). */
export function tabFromSegments(segments: string[]): Tab {
  return matchKnownTab(segments) ?? "tickets";
}

/** Parsea pathname + search a RouteState (normalizado). No toca window.
 *  NUNCA recibe el hash (#...): los callers pasan pathname+search; el hash está
 *  fuera del contrato (Stacky no usa anclas). */
export function parseRoute(pathname: string, search: string): RouteState {
  const segments = pathname.split("/").filter(Boolean); // filter(Boolean) descarta
                                                         // "" de doble-slash, raíz y trailing slash
  const known = matchKnownTab(segments);
  const tab = known ?? "tickets";
  // C4: subtab SOLO si el 1er segmento es un tab CONOCIDO. Con tab desconocido
  // ("/nonexistent/foo") o raíz, subtab queda undefined — si no, el round-trip
  // serializaría "/foo" y el re-parse perdería el subtab (rompe la idempotencia §4).
  // Corolario: "tickets" (raíz "/") JAMÁS lleva subtab.
  const subtab = known && segments.length >= 2 ? segments[1] : undefined;

  const sp = new URLSearchParams(search);
  let exec: number | undefined;
  for (const k of EXEC_KEYS) {
    const raw = sp.get(k);
    if (raw != null) {
      // C4: SOLO enteros decimales no vacíos. Number("")===0, Number("0x10")===16
      // y Number("1.5")===1.5 son trampas: "?exec=" vacío abriría el drawer de la
      // ejecución 0. Regex estricta o exec queda undefined.
      if (/^\d+$/.test(raw)) exec = parseInt(raw, 10);
      break;  // la PRIMERA clave presente DECIDE; si vienen ambas (?exec=1&execution=2),
              // la segunda se ignora y NO pasa a query (ambas están en EXEC_KEYS).
    }
  }
  const query: Record<string, string> = {};
  sp.forEach((v, k) => { if (!EXEC_KEYS.includes(k as typeof EXEC_KEYS[number])) query[k] = v; });

  return normalizeInitial({ tab, subtab, exec, query });
}

/** Backward-compat: el backend emite `/?exec=` en la RAÍZ, pero el drawer vive en
 *  el Historial. Si hay exec y el tab no es "history", normalizamos a "history"
 *  para que el drawer efectivamente se abra (hoy ese link no hace NADA). */
function normalizeInitial(s: RouteState): RouteState {
  if (s.exec != null && s.tab !== "history") return { ...s, tab: "history" };
  return s;
}

/** Serializa RouteState a una URL canónica (path + "?" + querystring ordenado). */
export function serializeRoute(s: RouteState): string {
  const base = TAB_PATHS[s.tab];                          // "/", "/history", "/settings", ...
  // C4: "tickets" (base "/") JAMÁS lleva subtab — "/x" colisionaría con el espacio de
  // tabs desconocidos y el round-trip no sería idempotente. Se descarta defensivo.
  const path = s.subtab && base !== "/"
    ? `${base}/${s.subtab}`                               // "/settings/appearance"
    : base;                                               // "/settings" | "/"
  const sp = new URLSearchParams();
  // query preservada primero, con claves ordenadas (round-trip estable/determinista)
  Object.keys(s.query).sort().forEach((k) => sp.set(k, s.query[k]));
  if (s.exec != null) sp.set("exec", String(s.exec));     // SIEMPRE clave canónica "exec"
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}

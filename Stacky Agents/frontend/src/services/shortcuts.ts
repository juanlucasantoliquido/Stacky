// Plan 172 F1 — Registro de atajos de teclado. PURO: cero imports de react o DOM.
//
// El sistema anterior tenía dos verdades: los atajos que App.tsx realmente
// escuchaba, y una lista escrita a mano en el overlay de ayuda que decía otra
// cosa. Acá hay una sola fuente: lo que está registrado es lo que funciona y lo
// que el overlay muestra.
//
// El matcher absorbe `matches()` del hook `useKeyboardShortcuts` (que quedó sin
// consumidores) y le corrige un bug: exigía shift ANTES de mirar la tecla, así
// que el combo "?" no podía matchear nunca. El comportamiento que se preserva es
// el de App.tsx, que sí funcionaba.

export type ShortcutScope = "global" | "page" | "dialog";
export type ShortcutCategory = "global" | "navegacion" | "listas";

export interface KeyEventLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

export interface ShortcutDef {
  id: string;
  combo: string;
  scope: ShortcutScope;
  category: ShortcutCategory;
  description: string;
  /** Preexistente al plan: sigue funcionando aunque la flag esté OFF. */
  core?: boolean;
  /** Por default un atajo NO dispara con un diálogo abierto. */
  allowInDialog?: boolean;
  /** Solo para el overlay: el handler vive en el contenedor de la lista. */
  displayOnly?: boolean;
  handler?: () => void;
}

export interface DispatchCtx {
  editable: boolean;
  dialogOpen: boolean;
  enabled: boolean;
}

export type CoreShortcutSpec = Omit<ShortcutDef, "handler">;

const SCOPE_PRIORITY: Record<ShortcutScope, number> = { dialog: 0, page: 1, global: 2 };

const CATEGORY_ORDER: ShortcutCategory[] = ["global", "navegacion", "listas"];
const CATEGORY_LABEL: Record<ShortcutCategory, string> = {
  global: "Global",
  navegacion: "Navegación",
  listas: "Listas",
};

// ── Parsing y matching ──────────────────────────────────────────────────────

export function parseCombo(combo: string): {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  key: string;
} {
  const partes = String(combo || "").split("+").map((p) => p.trim().toLowerCase());
  const key = partes.length ? partes[partes.length - 1] : "";
  return {
    ctrl: partes.includes("ctrl") || partes.includes("cmd") || partes.includes("meta"),
    shift: partes.includes("shift"),
    alt: partes.includes("alt"),
    key,
  };
}

function normalizeKey(key: string): string {
  const k = String(key || "").toLowerCase();
  if (k === "esc" || k === "escape") return "escape";
  return k;
}

export function eventMatchesCombo(ev: KeyEventLike, combo: string): boolean {
  const want = parseCombo(combo);
  const ctrlPresionado = Boolean(ev.ctrlKey || ev.metaKey);

  if (want.ctrl !== ctrlPresionado) return false;
  if (want.alt !== Boolean(ev.altKey)) return false;

  // "?" se produce con Shift+/ en la mayoría de los layouts: exigir shift acá es
  // lo que hacía que el combo no matcheara nunca.
  if (want.key === "?") {
    if (want.shift && !ev.shiftKey) return false;
    return ev.key === "?" || (Boolean(ev.shiftKey) && ev.key === "/");
  }

  if (want.shift !== Boolean(ev.shiftKey)) return false;
  return normalizeKey(ev.key) === normalizeKey(want.key);
}

export function isEditableTarget(
  tagName: string,
  isContentEditable: boolean | undefined
): boolean {
  // Paridad EXACTA con App.tsx: SELECT no cuenta. Agregarlo cambiaría el
  // comportamiento actual, que es justo lo que este plan promete no hacer.
  return ["INPUT", "TEXTAREA"].includes(String(tagName || "").toUpperCase())
    || isContentEditable === true;
}

export function comboAllowedInEditable(combo: string): boolean {
  // Dentro de un input, una tecla suelta es texto que el operador está
  // escribiendo. Solo los combos con modificador siguen siendo atajos.
  return parseCombo(combo).ctrl;
}

// ── Resolución ──────────────────────────────────────────────────────────────

export function resolveShortcut(
  defs: ShortcutDef[],
  ev: KeyEventLike,
  ctx: DispatchCtx
): ShortcutDef | null {
  const candidatos = (defs || []).filter((d) => {
    if (!d || d.displayOnly) return false;
    if (!ctx.enabled && !d.core) return false;
    if (ctx.dialogOpen && !d.allowInDialog) return false;
    if (ctx.editable && !comboAllowedInEditable(d.combo)) return false;
    return eventMatchesCombo(ev, d.combo);
  });

  if (!candidatos.length) return null;

  // Estable: ante igual prioridad de scope gana el primero registrado.
  let mejor = candidatos[0];
  for (const c of candidatos.slice(1)) {
    if (SCOPE_PRIORITY[c.scope] < SCOPE_PRIORITY[mejor.scope]) mejor = c;
  }
  return mejor;
}

export function detectCollisions(defs: ShortcutDef[]): string[][] {
  const porClave = new Map<string, string[]>();
  for (const d of defs || []) {
    if (!d) continue;
    const clave = `${parseCombo(d.combo).key}|${d.combo.toLowerCase()}|${d.scope}`;
    porClave.set(clave, [...(porClave.get(clave) || []), d.id]);
  }
  return [...porClave.values()].filter((ids) => ids.length > 1);
}

// ── Datos del overlay ───────────────────────────────────────────────────────

export function visibleShortcuts(defs: ShortcutDef[], enabled: boolean): ShortcutDef[] {
  // Con la flag OFF el overlay muestra exactamente lo que funciona. Un overlay
  // que promete atajos muertos es peor que no tener overlay.
  return (defs || []).filter((d) => enabled || d.core);
}

export function comboLabel(combo: string): string {
  return String(combo || "");
}

export function groupForOverlay(defs: ShortcutDef[]): {
  category: ShortcutCategory;
  label: string;
  items: { comboLabel: string; description: string }[];
}[] {
  const vistos = new Set<string>();
  const unicos = (defs || []).filter((d) => {
    if (!d || vistos.has(d.id)) return false;
    vistos.add(d.id);
    return true;
  });

  return CATEGORY_ORDER.map((category) => ({
    category,
    label: CATEGORY_LABEL[category],
    items: unicos
      .filter((d) => d.category === category)
      .map((d) => ({ comboLabel: comboLabel(d.combo), description: d.description })),
  })).filter((g) => g.items.length > 0);
}

export function withShortcutHint(base: string, hint: string, enabled: boolean): string {
  return enabled && hint ? `${base} · ${hint}` : base;
}

// ── Defs estáticos ──────────────────────────────────────────────────────────

/** Los 3 atajos que ya existían antes del plan. Sin handler: lo adjunta App.tsx
 *  por id, para que la declaración viva en un solo lugar y el test de colisiones
 *  mire el array REAL y no una copia a mano. */
export const CORE_SHORTCUT_DEFS: CoreShortcutSpec[] = [
  {
    id: "palette.toggle",
    combo: "Ctrl+K",
    scope: "global",
    category: "global",
    description: "Abrir la paleta de comandos",
    core: true,
    allowInDialog: true,
  },
  {
    id: "help.shortcuts",
    combo: "?",
    scope: "global",
    category: "global",
    description: "Mostrar esta ayuda de atajos",
    core: true,
    allowInDialog: true,
  },
  {
    id: "nav.toggle-board",
    // Ctrl+/ es el binding REAL desde el plan 136: cambiarlo acá al migrar
    // habría rebindeado en silencio una tecla que el operador ya usa.
    combo: "Ctrl+/",
    scope: "global",
    category: "navegacion",
    description: "Alternar entre Mi Equipo y Tickets",
    core: true,
    allowInDialog: true,
  },
];

/** Navegación de listas: el overlay las documenta, el dispatch las ignora
 *  (cada contenedor maneja su propio foco). */
export const LIST_NAV_DISPLAY_DEFS: ShortcutDef[] = [
  { id: "list.next", combo: "J", scope: "page", category: "listas", displayOnly: true, description: "Fila siguiente (también ↓)" },
  { id: "list.prev", combo: "K", scope: "page", category: "listas", displayOnly: true, description: "Fila anterior (también ↑)" },
  { id: "list.first", combo: "Home", scope: "page", category: "listas", displayOnly: true, description: "Primera fila" },
  { id: "list.last", combo: "End", scope: "page", category: "listas", displayOnly: true, description: "Última fila" },
  { id: "list.open", combo: "Enter", scope: "page", category: "listas", displayOnly: true, description: "Abrir el detalle de la fila" },
  { id: "list.close", combo: "Escape", scope: "page", category: "listas", displayOnly: true, description: "Cerrar el detalle abierto" },
];

// ── Registro ────────────────────────────────────────────────────────────────

const _defs = new Map<string, ShortcutDef>();

export const shortcutRegistry = {
  /** Reemplaza por id: registrar dos veces el mismo atajo es idempotente, que es
   *  lo que hace falta para sobrevivir al doble montaje de StrictMode. */
  register(def: ShortcutDef): void {
    if (!def || !def.id) return;
    _defs.set(def.id, def);
  },
  unregister(id: string): void {
    _defs.delete(id);
  },
  getAll(): ShortcutDef[] {
    return [..._defs.values()];
  },
  /** true si matcheó y ejecutó. El preventDefault lo hace el listener, no acá:
   *  un módulo puro no toca el evento del DOM. */
  dispatch(ev: KeyEventLike, ctx: DispatchCtx): boolean {
    const def = resolveShortcut(shortcutRegistry.getAll(), ev, ctx);
    if (!def || !def.handler) return false;
    try {
      def.handler();
    } catch {
      // Un atajo que revienta no puede dejar el teclado inservible.
      return true;
    }
    return true;
  },
};

let _enabled = true;

export function setUiShortcutsEnabled(v: boolean): void {
  _enabled = Boolean(v);
}

export function isUiShortcutsEnabled(): boolean {
  return _enabled;
}

/** Guardia de desarrollo: avisa si dos atajos pelean por el mismo combo.
 *  Cero costo en producción; delata regresiones que ningún grep ve. */
export function assertNoRuntimeCollisions(): void {
  const grupos = detectCollisions(shortcutRegistry.getAll());
  if (grupos.length) {
    // eslint-disable-next-line no-console
    console.warn("[shortcuts] combos en colisión:", grupos);
  }
}

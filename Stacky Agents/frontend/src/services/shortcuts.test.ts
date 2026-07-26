// Plan 172 F1 — El corazón del sistema de atajos, puro y sin DOM.
// Toda la semántica queda clavada acá ANTES de tocar un componente.
import { describe, it, expect, beforeEach } from "vitest";
import {
  CORE_SHORTCUT_DEFS,
  LIST_NAV_DISPLAY_DEFS,
  comboAllowedInEditable,
  comboLabel,
  detectCollisions,
  eventMatchesCombo,
  groupForOverlay,
  isEditableTarget,
  parseCombo,
  resolveShortcut,
  shortcutRegistry,
  visibleShortcuts,
  withShortcutHint,
  type KeyEventLike,
  type ShortcutDef,
} from "./shortcuts";

function ev(over: Partial<KeyEventLike> = {}): KeyEventLike {
  return { key: "a", ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...over };
}

const CTX = { editable: false, dialogOpen: false, enabled: true };

function def(over: Partial<ShortcutDef> = {}): ShortcutDef {
  return {
    id: "x.y",
    combo: "Ctrl+K",
    scope: "global",
    category: "global",
    description: "algo",
    handler: () => {},
    ...over,
  };
}

describe("parseCombo", () => {
  it("separa modificadores y tecla", () => {
    expect(parseCombo("Ctrl+Shift+K")).toEqual({ ctrl: true, shift: true, alt: false, key: "k" });
  });

  it("trata Cmd como Ctrl (Mac)", () => {
    expect(parseCombo("Cmd+K").ctrl).toBe(true);
  });

  it("un combo sin modificadores es solo la tecla", () => {
    expect(parseCombo("?")).toEqual({ ctrl: false, shift: false, alt: false, key: "?" });
  });
});

describe("eventMatchesCombo", () => {
  it("match_ctrl_k", () => {
    expect(eventMatchesCombo(ev({ key: "k", ctrlKey: true }), "Ctrl+K")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "k", metaKey: true }), "Ctrl+K")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "k" }), "Ctrl+K")).toBe(false);
  });

  it("match_question_shift_fix", () => {
    // El hook viejo exigía shift ANTES de mirar la tecla, así que "?" no matcheaba
    // nunca. En la mayoría de los layouts "?" se produce con Shift+/.
    expect(eventMatchesCombo(ev({ key: "?", shiftKey: true }), "?")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "?" }), "?")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "/", shiftKey: true }), "?")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "/" }), "?")).toBe(false);
    expect(eventMatchesCombo(ev({ key: "?", ctrlKey: true }), "?")).toBe(false);
  });

  it("normaliza Enter y Escape", () => {
    expect(eventMatchesCombo(ev({ key: "Enter" }), "Enter")).toBe(true);
    expect(eventMatchesCombo(ev({ key: "Escape" }), "Esc")).toBe(true);
  });

  it("la tecla es case-insensitive", () => {
    expect(eventMatchesCombo(ev({ key: "J" }), "j")).toBe(true);
  });

  it("un modificador de más no matchea", () => {
    expect(eventMatchesCombo(ev({ key: "k", ctrlKey: true, altKey: true }), "Ctrl+K")).toBe(false);
  });
});

describe("supresión en campos editables", () => {
  it("editable_suppression", () => {
    expect(isEditableTarget("INPUT", undefined)).toBe(true);
    expect(isEditableTarget("TEXTAREA", undefined)).toBe(true);
    expect(isEditableTarget("DIV", true)).toBe(true);
    expect(isEditableTarget("DIV", false)).toBe(false);
    // SELECT NO cuenta a propósito: hoy no está y agregarlo cambiaría el comportamiento.
    expect(isEditableTarget("SELECT", undefined)).toBe(false);
  });

  it("solo los combos con modificador sobreviven dentro de un input", () => {
    expect(comboAllowedInEditable("Ctrl+K")).toBe(true);
    expect(comboAllowedInEditable("Cmd+/")).toBe(true);
    expect(comboAllowedInEditable("?")).toBe(false);
    expect(comboAllowedInEditable("J")).toBe(false);
  });
});

describe("resolveShortcut", () => {
  it("resolve_gate_flag_off", () => {
    const nuevo = def({ id: "nuevo" });
    const core = def({ id: "core", core: true });

    expect(resolveShortcut([nuevo], ev({ key: "k", ctrlKey: true }), { ...CTX, enabled: false })).toBeNull();
    expect(resolveShortcut([core], ev({ key: "k", ctrlKey: true }), { ...CTX, enabled: false })?.id).toBe("core");
  });

  it("resolve_dialog_open", () => {
    const normal = def({ id: "normal" });
    const permitido = def({ id: "permitido", allowInDialog: true });

    expect(resolveShortcut([normal], ev({ key: "k", ctrlKey: true }), { ...CTX, dialogOpen: true })).toBeNull();
    expect(resolveShortcut([permitido], ev({ key: "k", ctrlKey: true }), { ...CTX, dialogOpen: true })?.id)
      .toBe("permitido");
  });

  it("resolve_editable", () => {
    const pregunta = def({ id: "q", combo: "?" });
    const paleta = def({ id: "p", combo: "Ctrl+K" });

    expect(resolveShortcut([pregunta], ev({ key: "?" }), { ...CTX, editable: true })).toBeNull();
    expect(resolveShortcut([paleta], ev({ key: "k", ctrlKey: true }), { ...CTX, editable: true })?.id).toBe("p");
  });

  it("scope_priority", () => {
    const global = def({ id: "g", scope: "global" });
    const pagina = def({ id: "p", scope: "page" });

    expect(resolveShortcut([global, pagina], ev({ key: "k", ctrlKey: true }), CTX)?.id).toBe("p");
  });

  it("los display-only nunca resuelven", () => {
    const soloOverlay = def({ id: "d", combo: "J", displayOnly: true, handler: undefined });

    expect(resolveShortcut([soloOverlay], ev({ key: "j" }), CTX)).toBeNull();
  });

  it("ante el mismo combo y scope gana el primero registrado", () => {
    const a = def({ id: "a" });
    const b = def({ id: "b" });

    expect(resolveShortcut([a, b], ev({ key: "k", ctrlKey: true }), CTX)?.id).toBe("a");
  });
});

describe("colisiones y defs estáticos", () => {
  it("collisions_zero_en_estaticos", () => {
    // Importa los arrays REALES: un atajo colisionante futuro rompe este test.
    expect(detectCollisions([...CORE_SHORTCUT_DEFS, ...LIST_NAV_DISPLAY_DEFS] as ShortcutDef[]))
      .toEqual([]);
  });

  it("detecta un choque real", () => {
    const grupos = detectCollisions([def({ id: "a" }), def({ id: "b" })]);

    expect(grupos).toEqual([["a", "b"]]);
  });

  it("core_defs_shape", () => {
    expect(CORE_SHORTCUT_DEFS.map((d) => d.id).sort()).toEqual(
      ["help.shortcuts", "nav.toggle-board", "palette.toggle"]
    );
    for (const d of CORE_SHORTCUT_DEFS) {
      expect(d.core).toBe(true);
      expect(d.allowInDialog).toBe(true);
      // El handler lo adjunta App.tsx: acá solo vive la declaración.
      expect("handler" in d).toBe(false);
    }
  });

  it("los combos core son los REALES, no unos parecidos", () => {
    // Estos tres bindings ya existían antes del registro. Migrarlos con un
    // combo distinto rebindearía en silencio una tecla que el operador usa
    // todos los días — y el shape del def se vería perfectamente sano.
    const porId = Object.fromEntries(CORE_SHORTCUT_DEFS.map((d) => [d.id, d.combo]));

    expect(porId).toEqual({
      "palette.toggle": "Ctrl+K",
      "help.shortcuts": "?",
      "nav.toggle-board": "Ctrl+/",
    });
  });

  it("los defs de lista son todos display-only", () => {
    expect(LIST_NAV_DISPLAY_DEFS).toHaveLength(6);
    for (const d of LIST_NAV_DISPLAY_DEFS) {
      expect(d.displayOnly).toBe(true);
      expect(d.scope).toBe("page");
      expect(d.category).toBe("listas");
    }
  });
});

describe("registro", () => {
  beforeEach(() => {
    for (const d of shortcutRegistry.getAll()) shortcutRegistry.unregister(d.id);
  });

  it("registry_replace_by_id", () => {
    const a = def({ id: "uno" });
    shortcutRegistry.register(a);
    shortcutRegistry.register({ ...a, description: "otra" });

    expect(shortcutRegistry.getAll()).toHaveLength(1);
    expect(shortcutRegistry.getAll()[0].description).toBe("otra");
  });

  it("dispatch ejecuta el handler y avisa que matcheó", () => {
    let veces = 0;
    shortcutRegistry.register(def({ id: "d", handler: () => { veces += 1; } }));

    const matcheo = shortcutRegistry.dispatch(ev({ key: "k", ctrlKey: true }), CTX);

    expect(matcheo).toBe(true);
    expect(veces).toBe(1);
  });

  it("dispatch devuelve false si nada matchea", () => {
    expect(shortcutRegistry.dispatch(ev({ key: "z" }), CTX)).toBe(false);
  });

  it("un handler que revienta no rompe el dispatch", () => {
    shortcutRegistry.register(def({ id: "boom", handler: () => { throw new Error("x"); } }));

    expect(() => shortcutRegistry.dispatch(ev({ key: "k", ctrlKey: true }), CTX)).not.toThrow();
  });

  it("unregister saca el atajo", () => {
    shortcutRegistry.register(def({ id: "tmp" }));
    shortcutRegistry.unregister("tmp");

    expect(shortcutRegistry.getAll()).toHaveLength(0);
  });
});

describe("datos del overlay", () => {
  it("visible_off_solo_core", () => {
    const defs = [def({ id: "core", core: true }), def({ id: "nuevo" })];

    expect(visibleShortcuts(defs, false).map((d) => d.id)).toEqual(["core"]);
    expect(visibleShortcuts(defs, true)).toHaveLength(2);
  });

  it("group_for_overlay", () => {
    const grupos = groupForOverlay([
      def({ id: "l", combo: "J", category: "listas" }),
      def({ id: "g", category: "global" }),
      def({ id: "n", combo: "Ctrl+B", category: "navegacion" }),
      def({ id: "g" }), // duplicado por id
    ]);

    expect(grupos.map((g) => g.category)).toEqual(["global", "navegacion", "listas"]);
    expect(grupos.map((g) => g.label)).toEqual(["Global", "Navegación", "Listas"]);
    expect(grupos[0].items).toHaveLength(1);
  });

  it("no arma grupos vacíos", () => {
    const grupos = groupForOverlay([def({ id: "g", category: "global" })]);

    expect(grupos).toHaveLength(1);
  });

  it("comboLabel deja el combo legible", () => {
    expect(comboLabel("Ctrl+K")).toBe("Ctrl+K");
    expect(comboLabel("?")).toBe("?");
  });

  it("with_shortcut_hint", () => {
    expect(withShortcutHint("Buscar", "Ctrl+K", true)).toBe("Buscar · Ctrl+K");
    expect(withShortcutHint("Buscar", "Ctrl+K", false)).toBe("Buscar");
  });
});

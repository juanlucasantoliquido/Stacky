// Plan 173 F2 — Vistas guardadas (lógica pura).
import { describe, it, expect } from "vitest";
import {
  applyView,
  computeActiveView,
  deleteView,
  EMPTY_SAVED_VIEWS,
  filtersToTicketBoardState,
  MAX_VIEWS_PER_SCREEN,
  normalizeFilters,
  renameView,
  sanitizeSavedViews,
  ticketBoardStateToFilters,
  upsertView,
  validateViewName,
  type SavedViewsState,
} from "../savedViews";

function estado(nombres: string[], lastApplied: string | null = null): SavedViewsState {
  return { views: nombres.map((n) => ({ name: n, filters: { q: n } })), lastApplied };
}

describe("normalizeFilters", () => {
  it("descarta los vacíos y ordena las claves", () => {
    // Dos filtros iguales escritos en distinto orden tienen que dar el MISMO
    // preset, si no computeActiveView no matchearía nunca.
    expect(normalizeFilters({ z: "1", a: "2", vacio: "" })).toEqual({ a: "2", z: "1" });
    expect(Object.keys(normalizeFilters({ z: "1", a: "2" }))).toEqual(["a", "z"]);
  });
});

describe("validateViewName", () => {
  it("rechaza el vacío y el que es solo espacios", () => {
    expect(validateViewName("   ", EMPTY_SAVED_VIEWS)).toBe("El nombre no puede estar vacío");
  });

  it("rechaza los muy largos", () => {
    expect(validateViewName("x".repeat(61), EMPTY_SAVED_VIEWS)).toBe("Máximo 60 caracteres");
  });

  it("el duplicado no distingue mayúsculas", () => {
    expect(validateViewName("MÍOS", estado(["míos"]))).toBe("Ya existe una vista con ese nombre");
  });

  it("renombrar a sí mismo es válido", () => {
    expect(validateViewName("míos", estado(["míos"]), "míos")).toBeNull();
  });

  it("con el cupo lleno no entra una nueva", () => {
    const lleno = estado(Array.from({ length: MAX_VIEWS_PER_SCREEN }, (_, i) => `v${i}`));

    expect(validateViewName("nueva", lleno)).toBe("Máximo 20 vistas por pantalla");
  });

  it("pero SÍ se puede reemplazar una propia con el cupo lleno", () => {
    // Si no, llegado al tope el operador no podría ni actualizar sus presets.
    const lleno = estado(Array.from({ length: MAX_VIEWS_PER_SCREEN }, (_, i) => `v${i}`));

    expect(validateViewName("v3", lleno, "v3")).toBeNull();
  });

  it("un nombre válido no devuelve mensaje", () => {
    expect(validateViewName("  Míos  ", EMPTY_SAVED_VIEWS)).toBeNull();
  });
});

describe("upsertView", () => {
  it("agrega y normaliza los filtros", () => {
    const s = upsertView(EMPTY_SAVED_VIEWS, "  Míos ", { b: "2", a: "1", x: "" });

    expect(s.views).toEqual([{ name: "Míos", filters: { a: "1", b: "2" } }]);
  });

  it("reemplaza por nombre sin duplicar ni mover de lugar", () => {
    const s = upsertView(estado(["a", "b", "c"]), "b", { q: "nuevo" });

    expect(s.views.map((v) => v.name)).toEqual(["a", "b", "c"]);
    expect(s.views[1].filters).toEqual({ q: "nuevo" });
  });

  it("no muta el estado que recibe", () => {
    const original = estado(["a"]);
    const copia = JSON.parse(JSON.stringify(original));

    upsertView(original, "b", { q: "1" });

    expect(original).toEqual(copia);
  });
});

describe("renameView y deleteView", () => {
  it("renombrar arrastra el preset activo", () => {
    // Dejarlo apuntando al nombre viejo lo mostraría como "ninguno activo".
    const s = renameView(estado(["a", "b"], "a"), "a", "nuevo");

    expect(s.views.map((v) => v.name)).toEqual(["nuevo", "b"]);
    expect(s.lastApplied).toBe("nuevo");
  });

  it("renombrar otro no toca el activo", () => {
    expect(renameView(estado(["a", "b"], "b"), "a", "z").lastApplied).toBe("b");
  });

  it("borrar el activo lo deja en null", () => {
    const s = deleteView(estado(["a", "b"], "a"), "a");

    expect(s.views.map((v) => v.name)).toEqual(["b"]);
    expect(s.lastApplied).toBeNull();
  });

  it("borrar otro no toca el activo", () => {
    expect(deleteView(estado(["a", "b"], "b"), "a").lastApplied).toBe("b");
  });
});

describe("applyView", () => {
  it("devuelve los filtros y marca el activo", () => {
    const r = applyView(estado(["a", "b"]), "b");

    expect(r?.filters).toEqual({ q: "b" });
    expect(r?.state.lastApplied).toBe("b");
  });

  it("una vista inexistente devuelve null en vez de un estado vacío", () => {
    // Devolver filtros vacíos borraría los del operador sin que lo pidiera.
    expect(applyView(estado(["a"]), "no-existe")).toBeNull();
  });
});

describe("computeActiveView", () => {
  it("matchea el preset cuyos filtros coinciden", () => {
    expect(computeActiveView(estado(["a", "b"]), { q: "b" })).toBe("b");
  });

  it("el orden de las claves no importa", () => {
    const s: SavedViewsState = { views: [{ name: "x", filters: { a: "1", b: "2" } }], lastApplied: null };

    expect(computeActiveView(s, { b: "2", a: "1" })).toBe("x");
  });

  it("un filtro vacío de más no rompe el match", () => {
    const s: SavedViewsState = { views: [{ name: "x", filters: { a: "1" } }], lastApplied: null };

    expect(computeActiveView(s, { a: "1", otro: "" })).toBe("x");
  });

  it("si no coincide ninguno, null", () => {
    expect(computeActiveView(estado(["a"]), { q: "otro" })).toBeNull();
  });
});

describe("sanitizeSavedViews", () => {
  it("null y basura dan el estado vacío", () => {
    expect(sanitizeSavedViews(null)).toEqual(EMPTY_SAVED_VIEWS);
    expect(sanitizeSavedViews("texto")).toEqual(EMPTY_SAVED_VIEWS);
    expect(sanitizeSavedViews({ views: "no-es-array" })).toEqual(EMPTY_SAVED_VIEWS);
  });

  it("descarta SOLO la entrada rota, no las buenas", () => {
    // Perder las 19 vistas buenas por una mala sería el peor resultado posible.
    const r = sanitizeSavedViews({
      views: [
        { name: "buena", filters: { a: "1" } },
        { name: "", filters: {} },
        { name: "sin-filtros" },
        null,
        { name: "otra", filters: { b: "2" } },
      ],
    });

    expect(r.views.map((v) => v.name)).toEqual(["buena", "otra"]);
  });

  it("los filtros no-string se descartan campo por campo", () => {
    const r = sanitizeSavedViews({ views: [{ name: "x", filters: { a: "1", n: 5, o: {} } }] });

    expect(r.views[0].filters).toEqual({ a: "1" });
  });

  it("respeta el tope de 20", () => {
    const r = sanitizeSavedViews({
      views: Array.from({ length: 50 }, (_, i) => ({ name: `v${i}`, filters: {} })),
    });

    expect(r.views).toHaveLength(MAX_VIEWS_PER_SCREEN);
  });

  it("un lastApplied que no existe se limpia", () => {
    const r = sanitizeSavedViews({ views: [{ name: "a", filters: {} }], lastApplied: "fantasma" });

    expect(r.lastApplied).toBeNull();
  });

  it("un lastApplied que sí existe se conserva", () => {
    const r = sanitizeSavedViews({ views: [{ name: "a", filters: {} }], lastApplied: "a" });

    expect(r.lastApplied).toBe("a");
  });
});

describe("tablero de tickets", () => {
  it("ida y vuelta conserva el estado", () => {
    const s = { search: "pago", onlyPending: true, showAll: false, viewMode: "table" };

    expect(filtersToTicketBoardState(ticketBoardStateToFilters(s))).toEqual(s);
  });

  it("sin filtros guardados usa los defaults REALES del tablero", () => {
    // Inventar otros haría que aplicar un preset viejo cambie cosas que el
    // operador nunca guardó.
    expect(filtersToTicketBoardState({})).toEqual({
      search: "",
      onlyPending: false,
      showAll: true,
      viewMode: "graph",
    });
  });

  it("un false se guarda como \"0\", no como ausente", () => {
    // Ausente significa "usá el default", y el default de showAll es true: sin
    // el "0" explícito, guardar showAll apagado lo releería encendido.
    const f = ticketBoardStateToFilters({
      search: "",
      onlyPending: false,
      showAll: false,
      viewMode: "graph",
    });

    expect(f).toEqual({ onlyPending: "0", showAll: "0", viewMode: "graph" });
  });

  it("y ese preset se relee apagado", () => {
    expect(filtersToTicketBoardState({ showAll: "0" }).showAll).toBe(false);
  });
});

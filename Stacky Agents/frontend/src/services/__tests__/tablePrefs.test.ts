// Plan 173 F2 — Preferencias de tabla (lógica pura).
import { describe, it, expect } from "vitest";
import {
  cycleSort,
  EMPTY_TABLE_PREFS,
  HISTORY_COLUMNS,
  isColVisible,
  MAX_COL_WIDTH,
  MIN_COL_WIDTH,
  sanitizeTablePrefs,
  setColumnWidth,
  sortToQuery,
  SYSLOG_COLUMNS,
  historyPaginationView,
  toggleColumn,
  type TablePrefs,
} from "../tablePrefs";

const COLS = HISTORY_COLUMNS;

describe("isColVisible", () => {
  it("sin preferencia se ven todas", () => {
    // null es "no configuré nada", que NO es lo mismo que "oculté todo".
    for (const c of COLS) expect(isColVisible(EMPTY_TABLE_PREFS, c.id)).toBe(true);
  });

  it("con lista, solo las que están", () => {
    const p: TablePrefs = { ...EMPTY_TABLE_PREFS, visibleColumns: ["inicio", "estado"] };

    expect(isColVisible(p, "inicio")).toBe(true);
    expect(isColVisible(p, "costo")).toBe(false);
  });
});

describe("toggleColumn", () => {
  it("apagar una deja el resto", () => {
    const p = toggleColumn(EMPTY_TABLE_PREFS, "costo", COLS);

    expect(p.visibleColumns).not.toContain("costo");
    expect(p.visibleColumns).toContain("inicio");
  });

  it("volver a prenderla la repone en el orden del catálogo", () => {
    // Si volviera al final, el operador vería la tabla reordenarse sola.
    const apagada = toggleColumn(EMPTY_TABLE_PREFS, "agente", COLS);
    const prendida = toggleColumn(apagada, "agente", COLS);

    expect(prendida.visibleColumns).toEqual(COLS.map((c) => c.id));
  });

  it("NUNCA deja la tabla sin columnas", () => {
    const p: TablePrefs = { ...EMPTY_TABLE_PREFS, visibleColumns: ["inicio"] };

    expect(toggleColumn(p, "inicio", COLS)).toBe(p);
  });
});

describe("cycleSort", () => {
  it("null → asc → desc → null", () => {
    const a = cycleSort(EMPTY_TABLE_PREFS, "inicio", COLS);
    const b = cycleSort(a, "inicio", COLS);
    const c = cycleSort(b, "inicio", COLS);

    expect(a.sort).toEqual({ column: "inicio", dir: "asc" });
    expect(b.sort).toEqual({ column: "inicio", dir: "desc" });
    expect(c.sort).toBeNull();
  });

  it("cambiar de columna arranca en asc", () => {
    const desc = cycleSort(cycleSort(EMPTY_TABLE_PREFS, "inicio", COLS), "inicio", COLS);

    expect(cycleSort(desc, "estado", COLS).sort).toEqual({ column: "estado", dir: "asc" });
  });

  it("una columna sin sortKey no hace nada", () => {
    // Duración y costo no se pueden ordenar en el servidor: ofrecerlo sería
    // prometer un orden que nunca va a llegar.
    expect(cycleSort(EMPTY_TABLE_PREFS, "costo", COLS)).toBe(EMPTY_TABLE_PREFS);
    expect(cycleSort(EMPTY_TABLE_PREFS, "duracion", COLS)).toBe(EMPTY_TABLE_PREFS);
  });

  it("una columna inexistente tampoco", () => {
    expect(cycleSort(EMPTY_TABLE_PREFS, "fantasma", COLS)).toBe(EMPTY_TABLE_PREFS);
  });
});

describe("setColumnWidth", () => {
  it("clampea los extremos", () => {
    expect(setColumnWidth(EMPTY_TABLE_PREFS, "inicio", 5).widths.inicio).toBe(MIN_COL_WIDTH);
    expect(setColumnWidth(EMPTY_TABLE_PREFS, "inicio", 9999).widths.inicio).toBe(MAX_COL_WIDTH);
  });

  it("redondea a entero", () => {
    expect(setColumnWidth(EMPTY_TABLE_PREFS, "inicio", 120.7).widths.inicio).toBe(121);
  });

  it("no pisa los anchos de las otras", () => {
    const p = setColumnWidth(setColumnWidth(EMPTY_TABLE_PREFS, "inicio", 100), "estado", 200);

    expect(p.widths).toEqual({ inicio: 100, estado: 200 });
  });
});

describe("sanitizeTablePrefs", () => {
  it("null y basura dan las preferencias vacías", () => {
    expect(sanitizeTablePrefs(null, COLS)).toEqual(EMPTY_TABLE_PREFS);
    expect(sanitizeTablePrefs({ visibleColumns: "no-array" }, COLS)).toEqual(EMPTY_TABLE_PREFS);
  });

  it("descarta ids que ya no existen", () => {
    // Si mañana se renombra una columna, la preferencia vieja no puede dejar la
    // tabla sin ella para siempre.
    const p = sanitizeTablePrefs({ visibleColumns: ["inicio", "columna_vieja"] }, COLS);

    expect(p.visibleColumns).toEqual(["inicio"]);
  });

  it("si no queda ninguna válida, vuelve a 'todas'", () => {
    const p = sanitizeTablePrefs({ visibleColumns: ["nada", "cero"] }, COLS);

    expect(p.visibleColumns).toBeNull();
  });

  it("un sort sobre una columna no ordenable se descarta", () => {
    expect(sanitizeTablePrefs({ sort: { column: "costo", dir: "asc" } }, COLS).sort).toBeNull();
  });

  it("una dirección inventada se descarta", () => {
    expect(sanitizeTablePrefs({ sort: { column: "inicio", dir: "diagonal" } }, COLS).sort).toBeNull();
  });

  it("un sort válido sobrevive", () => {
    expect(sanitizeTablePrefs({ sort: { column: "inicio", dir: "desc" } }, COLS).sort).toEqual({
      column: "inicio",
      dir: "desc",
    });
  });

  it("los anchos se clampéan y los no-numéricos se van", () => {
    const p = sanitizeTablePrefs(
      { widths: { inicio: 9999, estado: -5, costo: "ancho", fantasma: 100 } },
      COLS,
    );

    expect(p.widths).toEqual({ inicio: MAX_COL_WIDTH, estado: MIN_COL_WIDTH });
  });
});

describe("sortToQuery", () => {
  it("sin orden no manda nada", () => {
    // Un sort vacío haría creer al backend que se le pidió un orden.
    expect(sortToQuery(EMPTY_TABLE_PREFS, COLS)).toEqual({});
  });

  it("traduce el id de columna a la clave del servidor", () => {
    const p: TablePrefs = { ...EMPTY_TABLE_PREFS, sort: { column: "inicio", dir: "desc" } };

    expect(sortToQuery(p, COLS)).toEqual({ sort: "started_at", dir: "desc" });
  });

  it("una columna sin sortKey no genera query", () => {
    const p: TablePrefs = { ...EMPTY_TABLE_PREFS, sort: { column: "costo", dir: "asc" } };

    expect(sortToQuery(p, COLS)).toEqual({});
  });
});

describe("catálogos", () => {
  it("los ids son únicos en cada tabla", () => {
    for (const cols of [HISTORY_COLUMNS, SYSLOG_COLUMNS]) {
      expect(new Set(cols.map((c) => c.id)).size).toBe(cols.length);
    }
  });

  it("el historial tiene 10 columnas", () => {
    expect(HISTORY_COLUMNS).toHaveLength(10);
  });

  it("los logs del sistema tienen las 11 columnas y ninguna ordenable", () => {
    expect(SYSLOG_COLUMNS).toHaveLength(11);
    expect(SYSLOG_COLUMNS.every((c) => !c.sortKey)).toBe(true);
  });
});

describe("historyPaginationView", () => {
  it("sin filtro de runtime usa el total del backend", () => {
    const v = historyPaginationView({ offset: 0, count: 20, limit: 20, total: 42, runtimeActive: false });

    expect(v.label).toBe("1–20 de 42");
    expect(v.canNext).toBe(true);
  });

  it("en la última página no deja avanzar", () => {
    const v = historyPaginationView({ offset: 40, count: 2, limit: 20, total: 42, runtimeActive: false });

    expect(v.label).toBe("41–42 de 42");
    expect(v.canNext).toBe(false);
  });

  it("con filtro de runtime IGNORA el total", () => {
    // El total del backend es el COUNT pre-filtro (el runtime se filtra después,
    // en Python): compararlo habilitaría "Siguiente" cuando ya no hay nada.
    const v = historyPaginationView({ offset: 0, count: 3, limit: 20, total: 42, runtimeActive: true });

    expect(v.label).toBe("1–3");
    expect(v.canNext).toBe(false);
  });

  it("con runtime y la página llena sí deja avanzar", () => {
    const v = historyPaginationView({ offset: 0, count: 20, limit: 20, total: 42, runtimeActive: true });

    expect(v.canNext).toBe(true);
  });

  it("un backend viejo sin total cae a la regla de siempre", () => {
    const lleno = historyPaginationView({ offset: 0, count: 20, limit: 20, total: null, runtimeActive: false });
    const parcial = historyPaginationView({ offset: 0, count: 7, limit: 20, total: null, runtimeActive: false });

    expect(lleno.label).toBe("1–20");
    expect(lleno.canNext).toBe(true);
    expect(parcial.canNext).toBe(false);
  });
});

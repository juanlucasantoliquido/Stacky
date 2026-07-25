// Plan 238 F4 — tests del modelo puro de la bandeja de incidencias.
import { describe, it, expect } from "vitest";
import {
  parseScope,
  sortIncidents,
  filterBySearch,
  countByState,
  formatIncidentsForCopy,
  summaryLabel,
  isProviderBlind,
  type IncidentInboxItem,
  type IncidentInboxResponse,
} from "./incidentInboxModel";

function it_(over: Partial<IncidentInboxItem> = {}): IncidentInboxItem {
  return {
    id: 1,
    ado_id: 1000,
    title: "Incidencia",
    work_item_type: "Issue",
    ado_state: "Active",
    ado_url: "https://tracker/1000",
    assigned_to_ado: null,
    stacky_status: "idle",
    last_synced_at: "2026-07-24T10:00:00",
    is_open: true,
    ...over,
  };
}

function res(over: Partial<IncidentInboxResponse> = {}): IncidentInboxResponse {
  return {
    ok: true,
    scope: "open",
    counts: { open: 0, closed: 0, total: 0 },
    truncated: false,
    untyped_count: 0,
    provider: "ado",
    incident_types: ["issue", "bug"],
    closed_states: ["Done"],
    items: [],
    ...over,
  };
}

describe("parseScope", () => {
  it("mapea todas las variantes de 'todas' a all y el resto a open", () => {
    expect(parseScope("all")).toBe("all");
    expect(parseScope("ALL")).toBe("all");
    expect(parseScope("todas")).toBe("all");
    expect(parseScope("open")).toBe("open");
    expect(parseScope(null)).toBe("open");
    expect(parseScope(undefined)).toBe("open");
    expect(parseScope("")).toBe("open");
    expect(parseScope("basura")).toBe("open");
  });
});

describe("sortIncidents", () => {
  it("pone abiertas primero", () => {
    const out = sortIncidents([it_({ ado_id: 1, is_open: false }), it_({ ado_id: 2, is_open: true })]);
    expect(out[0].is_open).toBe(true);
  });

  it("ordena por fecha desc dentro del grupo", () => {
    const out = sortIncidents([
      it_({ ado_id: 1, last_synced_at: "2026-07-01T00:00:00" }),
      it_({ ado_id: 2, last_synced_at: "2026-07-20T00:00:00" }),
    ]);
    expect(out.map((i) => i.ado_id)).toEqual([2, 1]);
  });

  it("desempata por ado_id desc", () => {
    const out = sortIncidents([
      it_({ ado_id: 5, last_synced_at: "2026-07-01T00:00:00" }),
      it_({ ado_id: 9, last_synced_at: "2026-07-01T00:00:00" }),
    ]);
    expect(out.map((i) => i.ado_id)).toEqual([9, 5]);
  });

  it("no muta la entrada", () => {
    const entrada = [it_({ ado_id: 1, is_open: false }), it_({ ado_id: 2, is_open: true })];
    const antes = entrada.map((i) => i.ado_id);
    sortIncidents(entrada);
    expect(entrada.map((i) => i.ado_id)).toEqual(antes);
  });

  it("tolera last_synced_at ausente", () => {
    const a = it_({ ado_id: 1 });
    const b = it_({ ado_id: 2 });
    delete a.last_synced_at;
    delete b.last_synced_at;
    const out = sortIncidents([a, b]);
    expect(out.map((i) => i.ado_id)).toEqual([2, 1]);
  });
});

describe("filterBySearch", () => {
  const items = [
    it_({ ado_id: 1234, title: "Error al guardar", ado_state: "Active" }),
    it_({ ado_id: 5678, title: "Pantalla en blanco", ado_state: "New" }),
  ];

  it("busca por titulo", () => {
    expect(filterBySearch(items, "GUARDAR").map((i) => i.ado_id)).toEqual([1234]);
  });

  it("busca por ado_id", () => {
    expect(filterBySearch(items, "1234").map((i) => i.ado_id)).toEqual([1234]);
  });

  it("busca por estado", () => {
    expect(filterBySearch(items, "activ").map((i) => i.ado_id)).toEqual([1234]);
  });

  it("vacio devuelve todo", () => {
    expect(filterBySearch(items, "")).toHaveLength(2);
    expect(filterBySearch(items, "   ")).toHaveLength(2);
  });
});

describe("countByState", () => {
  it("agrupa y ordena por cantidad desc", () => {
    const out = countByState([
      it_({ ado_state: "Active" }),
      it_({ ado_state: "Active" }),
      it_({ ado_state: "New" }),
    ]);
    expect(out).toEqual([
      { state: "Active", count: 2 },
      { state: "New", count: 1 },
    ]);
  });

  it("mapea el estado vacio", () => {
    const sin = it_();
    delete sin.ado_state;
    expect(countByState([sin])).toEqual([{ state: "(sin estado)", count: 1 }]);
  });
});

describe("formatIncidentsForCopy", () => {
  it("una linea por incidencia con 4 campos", () => {
    const out = formatIncidentsForCopy([it_({ ado_id: 1 }), it_({ ado_id: 2 })]);
    const lineas = out.split("\n");
    expect(lineas).toHaveLength(2);
    expect(lineas[0].split("\t")).toHaveLength(4);
  });

  it("lista vacia devuelve cadena vacia", () => {
    expect(formatIncidentsForCopy([])).toBe("");
  });
});

describe("summaryLabel", () => {
  it("respeta singular y plural", () => {
    expect(summaryLabel({ open: 1, closed: 2, total: 3 })).toBe("1 abierta de 3");
    expect(summaryLabel({ open: 2, closed: 1, total: 3 })).toBe("2 abiertas de 3");
  });
});

describe("isProviderBlind", () => {
  it("es true cuando no hay items pero si tickets sin tipo", () => {
    expect(isProviderBlind(res({ untyped_count: 5 }))).toBe(true);
  });

  it("es false si hay incidencias, si no hay sin-tipo, o si no hay respuesta", () => {
    expect(isProviderBlind(res({ untyped_count: 0 }))).toBe(false);
    expect(isProviderBlind(res({ untyped_count: 5, items: [it_()], counts: { open: 1, closed: 0, total: 1 } }))).toBe(false);
    expect(isProviderBlind(null)).toBe(false);
    expect(isProviderBlind(undefined)).toBe(false);
  });
});

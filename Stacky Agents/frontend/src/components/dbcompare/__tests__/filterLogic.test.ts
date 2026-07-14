import { describe, it, expect } from "vitest";
import { filterDiffItems, countByState, EMPTY_FILTERS } from "../filterLogic";
import type { DiffItem } from "../dbcompareTypes";

function item(partial: Partial<DiffItem>): DiffItem {
  return {
    object_type: "table",
    schema: "dbo",
    name: "T",
    action: "changed",
    severity: "warn",
    changes: [],
    ...partial,
  };
}

const CLIENTES = item({
  schema: "dbo",
  name: "CLIENTES",
  action: "changed",
  severity: "danger",
  changes: [{ kind: "column_type_changed", severity: "danger", detail: {} }],
});
const PRODUCTOS = item({ schema: "dbo", name: "PRODUCTOS", object_type: "table", action: "added", severity: "warn" });
const V_CLIENTES = item({
  schema: "dbo",
  name: "V_CLIENTES",
  object_type: "view",
  action: "changed",
  severity: "info",
  changes: [{ kind: "view_definition_changed", severity: "info", detail: {} }],
});

const FIXTURE = [CLIENTES, PRODUCTOS, V_CLIENTES];

describe("Plan 124 F5 — filterLogic (pure)", () => {
  it("filtros vacíos no filtran nada", () => {
    expect(filterDiffItems(FIXTURE, EMPTY_FILTERS)).toEqual(FIXTURE);
  });

  it("filtra por severidad", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, severities: ["warn"] });
    expect(out).toEqual([PRODUCTOS]);
  });

  it("filtra por tipo de objeto", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, objectTypes: ["view"] });
    expect(out).toEqual([V_CLIENTES]);
  });

  it("filtra por texto sobre el nombre", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, text: "produc" });
    expect(out).toEqual([PRODUCTOS]);
  });

  it("filtra por texto sobre el kind", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, text: "view_definition" });
    expect(out).toEqual([V_CLIENTES]);
  });

  it("KPI-2: severidad danger + texto CLIEN devuelve exactamente los items esperados", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, severities: ["danger"], text: "CLIEN" });
    expect(out).toEqual([CLIENTES]);
  });

  it("countByState cuenta por acción", () => {
    expect(countByState(FIXTURE)).toEqual({ added: 1, removed: 0, changed: 2 });
  });

  it("[integración F3] filtra por acción (stat tile de acción clickeado)", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, actions: ["added"] });
    expect(out).toEqual([PRODUCTOS]);
  });

  it("[integración F3] acciones vacías no filtran", () => {
    expect(filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, actions: [] })).toEqual(FIXTURE);
  });

  it("[integración F3] severidad + acción combinados", () => {
    const out = filterDiffItems(FIXTURE, { ...EMPTY_FILTERS, severities: ["danger", "info"], actions: ["changed"] });
    expect(out).toEqual([CLIENTES, V_CLIENTES]);
  });
});

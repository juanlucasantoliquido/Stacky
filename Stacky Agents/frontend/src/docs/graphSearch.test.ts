/**
 * graphSearch.test.ts — Plan 268 F2.1. Tests PUROS de la búsqueda rankeada.
 */
import { describe, it, expect } from "vitest";
import { searchGraphNodes, matchIdSet, matchAt } from "./graphSearch";
import type { DocGraphResponse, DocGraphNode } from "./docGraphModel";

function node(id: string, label: string, path: string): DocGraphNode {
  return {
    id,
    kind: "note",
    label,
    path,
    source_id: "s1",
    in_degree: 0,
    out_degree: 0,
    has_frontmatter: false,
    exists: true,
  };
}

function graphOf(nodes: DocGraphNode[]): DocGraphResponse {
  return {
    ok: true,
    generated_at: "2026-07-29T00:00:00+00:00",
    active_project: "TEST",
    sources: [],
    nodes,
    edges: [],
    orphans: [],
    stats: {},
    doc_health: null,
  };
}

describe("searchGraphNodes (plan 268 F2.1)", () => {
  const g = graphOf([
    node("n1", "Plan de despliegue.md", "docs/a/plan-de-despliegue.md"),
    node("n2", "Notas del plan.md", "docs/b/notas.md"),
    node("n3", "Otra cosa.md", "docs/c/con-plan-en-la-ruta.md"),
  ]);

  it("query vacia devuelve lista vacia", () => {
    expect(searchGraphNodes(g, "")).toEqual([]);
  });

  it("query de solo espacios devuelve lista vacia", () => {
    expect(searchGraphNodes(g, "   ")).toEqual([]);
  });

  it("grafo undefined devuelve lista vacia", () => {
    expect(searchGraphNodes(undefined, "plan")).toEqual([]);
  });

  it("prefijo del label rankea 3 y va primero", () => {
    const out = searchGraphNodes(g, "plan");
    expect(out[0].nodeId).toBe("n1");
    expect(out[0].rank).toBe(3);
  });

  it("substring del label rankea 2", () => {
    const out = searchGraphNodes(g, "plan");
    const m = out.find((x) => x.nodeId === "n2");
    expect(m?.rank).toBe(2);
  });

  it("coincidencia solo por path rankea 1 y va ultimo", () => {
    const out = searchGraphNodes(g, "plan");
    expect(out[out.length - 1].nodeId).toBe("n3");
    expect(out[out.length - 1].rank).toBe(1);
  });

  it("empate de rank ordena por path ascendente", () => {
    const g2 = graphOf([
      node("z", "plan uno", "docs/z.md"),
      node("a", "plan dos", "docs/a.md"),
    ]);
    expect(searchGraphNodes(g2, "plan").map((m) => m.nodeId)).toEqual(["a", "z"]);
  });

  it("empate de rank y path ordena por id ascendente", () => {
    const g2 = graphOf([
      node("b", "plan uno", "docs/mismo.md"),
      node("a", "plan dos", "docs/mismo.md"),
    ]);
    expect(searchGraphNodes(g2, "plan").map((m) => m.nodeId)).toEqual(["a", "b"]);
  });

  it("la busqueda es case-insensitive", () => {
    expect(searchGraphNodes(g, "PLAN").length).toBe(3);
    expect(searchGraphNodes(g, "  PlAn  ")[0].nodeId).toBe("n1");
  });

  it("query sin resultados devuelve lista vacia", () => {
    expect(searchGraphNodes(g, "zzzz-no-existe")).toEqual([]);
  });

  it("limit acota el numero de coincidencias", () => {
    expect(searchGraphNodes(g, "plan", 2).length).toBe(2);
    expect(searchGraphNodes(g, "plan", 0).length).toBe(0);
  });

  it("un label vacio solo matchea por path", () => {
    const g2 = graphOf([node("x", "", "docs/plan.md")]);
    const out = searchGraphNodes(g2, "plan");
    expect(out.length).toBe(1);
    expect(out[0].rank).toBe(1);
  });

  it("matchIdSet devuelve exactamente los ids de las coincidencias", () => {
    const out = searchGraphNodes(g, "plan");
    expect(matchIdSet(out)).toEqual(new Set(["n1", "n2", "n3"]));
    expect(matchIdSet([])).toEqual(new Set());
  });

  it("matchAt con lista vacia devuelve null", () => {
    expect(matchAt([], 0)).toBeNull();
    expect(matchAt([], 5)).toBeNull();
  });

  it("matchAt aplica modulo al indice fuera de rango", () => {
    const out = searchGraphNodes(g, "plan");
    expect(out.length).toBe(3);
    expect(matchAt(out, 7)).toBe(out[1].nodeId);
    expect(matchAt(out, 0)).toBe(out[0].nodeId);
  });

  it("matchAt con indice negativo devuelve null", () => {
    const out = searchGraphNodes(g, "plan");
    expect(matchAt(out, -1)).toBeNull();
  });

  it("con 5000 nodos la busqueda termina en menos de 2000 ms", () => {
    const nodes = Array.from({ length: 5000 }, (_, i) =>
      node(`n${i}`, `nota ${i}.md`, `docs/n${i}.md`)
    );
    const big = graphOf(nodes);
    const t0 = Date.now();
    const out = searchGraphNodes(big, "nota", 5000);
    const dt = Date.now() - t0;
    expect(out.length).toBe(5000);
    expect(dt).toBeLessThan(2000);
  });
});

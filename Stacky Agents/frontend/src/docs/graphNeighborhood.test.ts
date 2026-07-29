/**
 * graphNeighborhood.test.ts — Plan 268 F4.1. Tests PUROS del BFS de vecindario,
 * del sub-grafo enfocado, de la lista de relaciones y de resolveFocusId (C3/G13).
 */
import { describe, it, expect } from "vitest";
import {
  buildAdjacency,
  neighborhoodOf,
  focusSubgraph,
  rankedNeighbors,
  resolveFocusId,
} from "./graphNeighborhood";
import { collapseGroups, GROUP_NODE_PREFIX } from "./graphGrouping";
import { applyGraphFilters } from "./graphFilters";
import { EMPTY_FILTERS } from "./graphExplorerState";
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";

function node(id: string, overrides: Partial<DocGraphNode> = {}): DocGraphNode {
  return {
    id,
    kind: "note",
    label: id,
    path: `docs/${id}.md`,
    source_id: "s1",
    in_degree: 1,
    out_degree: 1,
    has_frontmatter: false,
    exists: true,
    ...overrides,
  };
}

function edge(source: string, target: string, kind: DocGraphEdge["kind"] = "md"): DocGraphEdge {
  return { source, target, kind };
}

function graphOf(
  nodes: DocGraphNode[],
  edges: DocGraphEdge[] = [],
  overrides: Partial<DocGraphResponse> = {}
): DocGraphResponse {
  return {
    ok: true,
    generated_at: "2026-07-29T00:00:00+00:00",
    active_project: "TEST",
    sources: [],
    nodes,
    edges,
    orphans: [],
    stats: {},
    doc_health: null,
    ...overrides,
  };
}

describe("buildAdjacency (plan 268 F4.1)", () => {
  it("buildAdjacency es no dirigida: A->B pone B en A y A en B", () => {
    const adj = buildAdjacency(graphOf([node("a"), node("b")], [edge("a", "b")]));
    expect(adj.get("a")).toEqual(new Set(["b"]));
    expect(adj.get("b")).toEqual(new Set(["a"]));
  });

  it("buildAdjacency ignora self-loops", () => {
    const adj = buildAdjacency(graphOf([node("a")], [edge("a", "a")]));
    expect(adj.get("a")).toBeUndefined();
  });

  it("buildAdjacency con grafo vacio devuelve Map vacio", () => {
    expect(buildAdjacency(graphOf([])).size).toBe(0);
    expect(buildAdjacency(undefined).size).toBe(0);
  });

  it("buildAdjacency ignora aristas a nodos que no existen", () => {
    const adj = buildAdjacency(graphOf([node("a")], [edge("a", "fantasma")]));
    expect(adj.size).toBe(0);
  });
});

describe("neighborhoodOf (plan 268 F4.1)", () => {
  // a - b - c ; d aislado ; e - f (otra componente)
  const g = graphOf(
    [node("a"), node("b"), node("c"), node("d"), node("e"), node("f")],
    [edge("a", "b"), edge("b", "c"), edge("e", "f")]
  );

  it("neighborhoodOf con rootId inexistente devuelve Set vacio", () => {
    expect(neighborhoodOf(g, "zzz", 2)).toEqual(new Set());
  });

  it("neighborhoodOf con rootId null devuelve Set vacio", () => {
    expect(neighborhoodOf(g, null, 2)).toEqual(new Set());
  });

  it("neighborhoodOf depth 0 devuelve solo el root", () => {
    expect(neighborhoodOf(g, "a", 0)).toEqual(new Set(["a"]));
  });

  it("neighborhoodOf depth negativo devuelve solo el root", () => {
    expect(neighborhoodOf(g, "a", -3)).toEqual(new Set(["a"]));
  });

  it("neighborhoodOf depth 1 devuelve root mas vecinos directos", () => {
    expect(neighborhoodOf(g, "a", 1)).toEqual(new Set(["a", "b"]));
  });

  it("neighborhoodOf depth 2 alcanza a los vecinos de los vecinos", () => {
    expect(neighborhoodOf(g, "a", 2)).toEqual(new Set(["a", "b", "c"]));
  });

  it("neighborhoodOf en un nodo sin aristas devuelve solo el root", () => {
    expect(neighborhoodOf(g, "d", 3)).toEqual(new Set(["d"]));
  });

  it("neighborhoodOf con un ciclo A-B-C-A no se cuelga", () => {
    const cyc = graphOf(
      [node("a"), node("b"), node("c")],
      [edge("a", "b"), edge("b", "c"), edge("c", "a")]
    );
    expect(neighborhoodOf(cyc, "a", 5)).toEqual(new Set(["a", "b", "c"]));
  });

  it("neighborhoodOf con depth mayor al diametro devuelve la componente conexa entera", () => {
    expect(neighborhoodOf(g, "a", 99)).toEqual(new Set(["a", "b", "c"]));
  });

  it("neighborhoodOf no cruza a otra componente desconectada", () => {
    const out = neighborhoodOf(g, "a", 99);
    expect(out.has("e")).toBe(false);
    expect(out.has("f")).toBe(false);
    expect(out.has("d")).toBe(false);
  });

  it("neighborhoodOf sobre 5000 nodos con depth 3 termina en menos de 2000 ms", () => {
    const nodes = Array.from({ length: 5000 }, (_, i) => node(`n${i}`));
    const edges = Array.from({ length: 10000 }, (_, i) =>
      edge(`n${i % 5000}`, `n${(i * 7 + 1) % 5000}`)
    );
    const big = graphOf(nodes, edges);
    const t0 = Date.now();
    const out = neighborhoodOf(big, "n0", 3);
    const dt = Date.now() - t0;
    expect(out.size).toBeGreaterThan(1);
    expect(dt).toBeLessThan(2000);
  });
});

describe("focusSubgraph (plan 268 F4.1)", () => {
  it("focusSubgraph conserva solo las aristas internas al vecindario", () => {
    const g = graphOf(
      [node("a"), node("b"), node("c")],
      [edge("a", "b"), edge("b", "c")]
    );
    const sub = focusSubgraph(g, "a", 1);
    expect(sub.nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(sub.edges.length).toBe(1);
    expect(sub.edges[0]).toEqual(edge("a", "b"));
  });

  it("focusSubgraph con root inexistente devuelve un grafo vacio", () => {
    const g = graphOf([node("a")], []);
    const sub = focusSubgraph(g, "zzz", 2);
    expect(sub.nodes).toEqual([]);
    expect(sub.edges).toEqual([]);
  });

  it("focusSubgraph recorta orphans a lo que queda", () => {
    const g = graphOf([node("a"), node("b"), node("z")], [edge("a", "b")], {
      orphans: ["b", "z"],
    });
    expect(focusSubgraph(g, "a", 1).orphans).toEqual(["b"]);
  });
});

describe("rankedNeighbors (plan 268 F4.1)", () => {
  it("rankedNeighbors lista primero los entrantes y despues los salientes", () => {
    // in: quien -> root ; out: root -> aquien
    const g = graphOf(
      [node("root", { path: "docs/root.md" }), node("in1"), node("out1")],
      [edge("in1", "root"), edge("root", "out1")]
    );
    const out = rankedNeighbors(g, "root");
    expect(out.map((e) => e.node.id)).toEqual(["in1", "out1"]);
    expect(out[0].direction).toBe("in");
    expect(out[1].direction).toBe("out");
  });

  it("rankedNeighbors marca direction both cuando hay arista en los dos sentidos", () => {
    const g = graphOf(
      [node("root"), node("x")],
      [edge("root", "x"), edge("x", "root")]
    );
    const out = rankedNeighbors(g, "root");
    expect(out.length).toBe(1);
    expect(out[0].direction).toBe("both");
  });

  it("rankedNeighbors agrupa los edgeKinds del mismo par de nodos", () => {
    const g = graphOf(
      [node("root"), node("x")],
      [edge("x", "root", "md"), edge("x", "root", "wikilink"), edge("x", "root", "md")]
    );
    const out = rankedNeighbors(g, "root");
    expect(out[0].edgeKinds).toEqual(["md", "wikilink"]);
  });

  it("rankedNeighbors ordena cada bloque por path ascendente", () => {
    const g = graphOf(
      [
        node("root"),
        node("z", { path: "docs/z.md" }),
        node("a", { path: "docs/a.md" }),
      ],
      [edge("z", "root"), edge("a", "root")]
    );
    expect(rankedNeighbors(g, "root").map((e) => e.node.id)).toEqual(["a", "z"]);
  });

  it("rankedNeighbors con root inexistente devuelve lista vacia", () => {
    expect(rankedNeighbors(graphOf([node("a")]), "zzz")).toEqual([]);
  });
});

describe("resolveFocusId (plan 268 F4.1 — C3/G13)", () => {
  it("resolveFocusId con focusRootId null devuelve null", () => {
    const g = graphOf([node("a")]);
    expect(resolveFocusId(g, g, null)).toBeNull();
  });

  it("resolveFocusId devuelve el mismo id si el nodo sigue en el grafo compuesto", () => {
    const g = graphOf([node("a"), node("b")]);
    expect(resolveFocusId(g, g, "a")).toBe("a");
  });

  it("resolveFocusId remapea al super-nodo cuando el grupo del nodo enfocado esta colapsado", () => {
    const original = graphOf([node("a", { source_id: "s1" }), node("b", { source_id: "s2" })]);
    // El grafo compuesto se arma a mano a propósito: así la regla 3 queda probada
    // COMPLETA en F4, sin depender de collapseGroups (que es F5).
    const composed = graphOf([
      node(`${GROUP_NODE_PREFIX}note:s1`, { label: "Notas · s1 (1)", path: "", source_id: "s1" }),
      node("b", { source_id: "s2" }),
    ]);
    expect(resolveFocusId(composed, original, "a")).toBe(`${GROUP_NODE_PREFIX}note:s1`);
  });

  it("resolveFocusId devuelve null si un filtro descarto el nodo enfocado", () => {
    const original = graphOf([node("a", { source_id: "s1" }), node("b", { source_id: "s2" })]);
    const composed = applyGraphFilters(original, { ...EMPTY_FILTERS, sourceIds: ["s2"] });
    expect(resolveFocusId(composed, original, "a")).toBeNull();
  });

  it("resolveFocusId nunca devuelve un id ausente del grafo compuesto", () => {
    const original = graphOf(
      Array.from({ length: 12 }, (_, i) => node(`n${i}`, { source_id: i % 2 ? "s1" : "s2" })),
      Array.from({ length: 11 }, (_, i) => edge(`n${i}`, `n${i + 1}`))
    );
    const combos: Array<{ sourceIds: string[]; collapsed: string[] }> = [];
    for (const sourceIds of [[], ["s1"], ["s2"], ["s1", "s2"]]) {
      for (const collapsed of [[], ["note:s1"], ["note:s2"], ["note:s1", "note:s2"], ["code"]]) {
        combos.push({ sourceIds, collapsed });
      }
    }
    expect(combos.length).toBe(20);
    for (const c of combos) {
      const composed = collapseGroups(
        applyGraphFilters(original, { ...EMPTY_FILTERS, sourceIds: c.sourceIds }),
        c.collapsed
      );
      const ids = new Set(composed.nodes.map((n) => n.id));
      for (const root of ["n0", "n1", "n11"]) {
        const r = resolveFocusId(composed, original, root);
        expect(r === null || ids.has(r)).toBe(true);
      }
    }
  });

  it("componer filtros + colapso + foco sobre el grupo del nodo enfocado NO devuelve un grafo vacio", () => {
    // (G13) El caso que prueba que el canvas nunca queda vacío.
    const original = graphOf(
      Array.from({ length: 12 }, (_, i) => node(`n${i}`, { source_id: i < 6 ? "s1" : "s2" })),
      Array.from({ length: 11 }, (_, i) => edge(`n${i}`, `n${i + 1}`))
    );
    const focusRootId = "n2"; // pertenece al grupo note:s1
    const filtered = applyGraphFilters(original, EMPTY_FILTERS);
    const grouped = collapseGroups(filtered, ["note:s1"]);
    const focusId = resolveFocusId(grouped, original, focusRootId);
    const visible = focusId ? focusSubgraph(grouped, focusId, 1) : grouped;
    expect(focusId).toBe(`${GROUP_NODE_PREFIX}note:s1`);
    expect(visible.nodes.length).toBeGreaterThan(0);
  });
});

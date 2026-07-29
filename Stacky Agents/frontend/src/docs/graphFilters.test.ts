/**
 * graphFilters.test.ts — Plan 268 F1.1. Tests PUROS del filtrado del grafo.
 */
import { describe, it, expect } from "vitest";
import { applyGraphFilters, availableFilterOptions, EMPTY_GRAPH } from "./graphFilters";
import { EMPTY_FILTERS, type GraphFilterState } from "./graphExplorerState";
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";

function node(
  id: string,
  overrides: Partial<DocGraphNode> = {}
): DocGraphNode {
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

function f(overrides: Partial<GraphFilterState> = {}): GraphFilterState {
  return { ...EMPTY_FILTERS, ...overrides };
}

describe("applyGraphFilters (plan 268 F1.1)", () => {
  it("sin filtros devuelve todos los nodos y aristas", () => {
    const g = graphOf([node("a"), node("b")], [edge("a", "b")]);
    const out = applyGraphFilters(g, EMPTY_FILTERS);
    expect(out.nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(out.edges.length).toBe(1);
  });

  it("sin filtros devuelve el MISMO objeto (identidad referencial, R2)", () => {
    // Sin esto, cada render crea un objeto nuevo, el efecto de layout se
    // re-ejecuta y el grafo se re-simula desde cero en cada tecleo.
    const g = graphOf([node("a")], []);
    expect(applyGraphFilters(g, EMPTY_FILTERS)).toBe(g);
  });

  it("grafo undefined devuelve EMPTY_GRAPH sin lanzar", () => {
    expect(() => applyGraphFilters(undefined, EMPTY_FILTERS)).not.toThrow();
    expect(applyGraphFilters(undefined, EMPTY_FILTERS)).toBe(EMPTY_GRAPH);
    expect(EMPTY_GRAPH.nodes).toEqual([]);
    expect(EMPTY_GRAPH.edges).toEqual([]);
  });

  it("grafo vacio devuelve nodes y edges vacios", () => {
    const out = applyGraphFilters(graphOf([]), f({ kinds: ["note"] }));
    expect(out.nodes).toEqual([]);
    expect(out.edges).toEqual([]);
  });

  it("filtrar por kind note descarta code y missing", () => {
    const g = graphOf([
      node("a"),
      node("c", { kind: "code", source_id: "" }),
      node("m", { kind: "missing", source_id: "" }),
    ]);
    const out = applyGraphFilters(g, f({ kinds: ["note"] }));
    expect(out.nodes.map((n) => n.id)).toEqual(["a"]);
  });

  it("filtrar por sourceId deja solo esa fuente", () => {
    const g = graphOf([node("a", { source_id: "s1" }), node("b", { source_id: "s2" })]);
    const out = applyGraphFilters(g, f({ sourceIds: ["s2"] }));
    expect(out.nodes.map((n) => n.id)).toEqual(["b"]);
  });

  it("un nodo code con source_id vacio pasa el filtro de fuente", () => {
    const g = graphOf([node("a", { source_id: "s1" }), node("c", { kind: "code", source_id: "" })]);
    const out = applyGraphFilters(g, f({ sourceIds: ["s2"] }));
    expect(out.nodes.map((n) => n.id)).toEqual(["c"]);
  });

  it("hideOrphans descarta los ids listados en graph.orphans", () => {
    const g = graphOf([node("a"), node("b")], [], { orphans: ["b"] });
    const out = applyGraphFilters(g, f({ hideOrphans: true }));
    expect(out.nodes.map((n) => n.id)).toEqual(["a"]);
  });

  it("onlyStale deja solo nodos con has_stale true", () => {
    const g = graphOf([node("a", { has_stale: true }), node("b", { has_stale: false })]);
    const out = applyGraphFilters(g, f({ onlyStale: true }));
    expect(out.nodes.map((n) => n.id)).toEqual(["a"]);
  });

  it("onlyStale con has_stale ausente (flag 114 OFF) deja 0 nodos", () => {
    const g = graphOf([node("a"), node("b")]);
    expect(applyGraphFilters(g, f({ onlyStale: true })).nodes).toEqual([]);
  });

  it("minDegree 1 descarta el nodo sin aristas", () => {
    const g = graphOf([
      node("a", { in_degree: 0, out_degree: 0 }),
      node("b", { in_degree: 1, out_degree: 0 }),
    ]);
    const out = applyGraphFilters(g, f({ minDegree: 1 }));
    expect(out.nodes.map((n) => n.id)).toEqual(["b"]);
  });

  it("una arista sobrevive solo si sus dos extremos sobreviven", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("b", { source_id: "s2" })],
      [edge("a", "b")]
    );
    const out = applyGraphFilters(g, f({ sourceIds: ["s1"] }));
    expect(out.nodes.map((n) => n.id)).toEqual(["a"]);
    expect(out.edges).toEqual([]);
  });

  it("filtrar por edgeKind wikilink descarta md y code_ref", () => {
    const g = graphOf(
      [node("a"), node("b")],
      [edge("a", "b", "md"), edge("a", "b", "wikilink"), edge("b", "a", "code_ref")]
    );
    const out = applyGraphFilters(g, f({ edgeKinds: ["wikilink"] }));
    expect(out.edges.length).toBe(1);
    expect(out.edges[0].kind).toBe("wikilink");
  });

  it("un ciclo A->B->A conserva ambas aristas", () => {
    const g = graphOf([node("a"), node("b")], [edge("a", "b"), edge("b", "a")]);
    const out = applyGraphFilters(g, f({ kinds: ["note"] }));
    expect(out.edges.length).toBe(2);
  });

  it("orphans se recorta a los nodos vivos", () => {
    const g = graphOf([node("a", { source_id: "s1" }), node("b", { source_id: "s2" })], [], {
      orphans: ["a", "b"],
    });
    const out = applyGraphFilters(g, f({ sourceIds: ["s1"] }));
    expect(out.orphans).toEqual(["a"]);
  });

  it("no muta el grafo de entrada", () => {
    const g = graphOf([node("a"), node("b", { source_id: "s2" })], [edge("a", "b")], {
      orphans: ["b"],
    });
    const snapshot = JSON.stringify(g);
    applyGraphFilters(g, f({ sourceIds: ["s1"], hideOrphans: true, minDegree: 1 }));
    expect(JSON.stringify(g)).toBe(snapshot);
  });

  it("conserva sources, stats y doc_health tal cual", () => {
    const g = graphOf([node("a"), node("b", { source_id: "s2" })], [], {
      sources: [
        { id: "s1", kind: "docs", label: "Fuente 1", relative_path: "docs", absolute_path: "/x/docs" },
      ],
      stats: { notes: 2 },
    });
    const out = applyGraphFilters(g, f({ sourceIds: ["s1"] }));
    expect(out.sources).toBe(g.sources);
    expect(out.stats).toBe(g.stats);
    expect(out.doc_health).toBe(g.doc_health);
  });

  it("applyGraphFilters con 5000 nodos termina en menos de 2000 ms", () => {
    const nodes = Array.from({ length: 5000 }, (_, i) =>
      node(`n${i}`, { source_id: i % 2 ? "s1" : "s2", in_degree: i % 7, out_degree: i % 3 })
    );
    const edges = Array.from({ length: 10000 }, (_, i) =>
      edge(`n${i % 5000}`, `n${(i * 7 + 1) % 5000}`, i % 2 ? "md" : "wikilink")
    );
    const g = graphOf(nodes, edges);
    const t0 = Date.now();
    const out = applyGraphFilters(g, f({ sourceIds: ["s1"], minDegree: 2, edgeKinds: ["md"] }));
    const dt = Date.now() - t0;
    expect(out.nodes.length).toBeGreaterThan(0);
    expect(dt).toBeLessThan(2000);
  });
});

describe("availableFilterOptions (plan 268 F1.1)", () => {
  it("availableFilterOptions cuenta nodos por fuente y por kind", () => {
    const g = graphOf([
      node("a", { source_id: "s1" }),
      node("b", { source_id: "s1" }),
      node("c", { kind: "code", source_id: "" }),
    ]);
    const o = availableFilterOptions(g);
    expect(o.sources).toEqual([{ value: "s1", label: "s1", count: 2 }]);
    expect(o.kinds.map((k) => [k.value, k.count])).toEqual([
      ["note", 2],
      ["code", 1],
      ["missing", 0],
    ]);
    expect(o.maxDegree).toBe(2);
  });

  it("availableFilterOptions con grafo vacio devuelve listas vacias y maxDegree 0", () => {
    for (const o of [availableFilterOptions(undefined), availableFilterOptions(graphOf([]))]) {
      expect(o.sources).toEqual([]);
      expect(o.kinds.length).toBe(3);
      expect(o.edgeKinds.length).toBe(3);
      expect(o.staleCount).toBe(0);
      expect(o.orphanCount).toBe(0);
      expect(o.maxDegree).toBe(0);
    }
  });

  it("availableFilterOptions toma el label de graph.sources y cae al id si no esta", () => {
    const g = graphOf([node("a", { source_id: "s1" }), node("b", { source_id: "zz" })], [], {
      sources: [
        { id: "s1", kind: "docs", label: "Alfa", relative_path: "d", absolute_path: "/d" },
      ],
    });
    const o = availableFilterOptions(g);
    expect(o.sources).toEqual([
      { value: "s1", label: "Alfa", count: 1 },
      { value: "zz", label: "zz", count: 1 },
    ]);
  });

  it("availableFilterOptions no lista fuentes con 0 nodos", () => {
    const g = graphOf([node("a", { source_id: "s1" })], [], {
      sources: [
        { id: "s1", kind: "docs", label: "Alfa", relative_path: "d", absolute_path: "/d" },
        { id: "s9", kind: "docs", label: "Vacia", relative_path: "v", absolute_path: "/v" },
      ],
    });
    expect(availableFilterOptions(g).sources.map((s) => s.value)).toEqual(["s1"]);
  });

  it("availableFilterOptions devuelve SIEMPRE los 3 kinds y los 3 edgeKinds, aun con count 0", () => {
    const o = availableFilterOptions(graphOf([node("a")]));
    expect(o.kinds.map((k) => k.value)).toEqual(["note", "code", "missing"]);
    expect(o.edgeKinds.map((k) => k.value)).toEqual(["md", "wikilink", "code_ref"]);
    expect(o.kinds.every((k) => k.label.length > 0)).toBe(true);
    expect(o.edgeKinds.every((k) => k.label.length > 0)).toBe(true);
  });

  it("availableFilterOptions cuenta stale y orphans", () => {
    const g = graphOf([node("a", { has_stale: true }), node("b")], [], { orphans: ["b"] });
    const o = availableFilterOptions(g);
    expect(o.staleCount).toBe(1);
    expect(o.orphanCount).toBe(1);
  });

  it("availableFilterOptions ordena fuentes por label y desempata por value", () => {
    const g = graphOf(
      [node("a", { source_id: "z" }), node("b", { source_id: "b" }), node("c", { source_id: "a" })],
      [],
      {
        sources: [
          { id: "z", kind: "d", label: "Igual", relative_path: "z", absolute_path: "/z" },
          { id: "b", kind: "d", label: "Igual", relative_path: "b", absolute_path: "/b" },
          { id: "a", kind: "d", label: "Antes", relative_path: "a", absolute_path: "/a" },
        ],
      }
    );
    expect(availableFilterOptions(g).sources.map((s) => s.value)).toEqual(["a", "b", "z"]);
  });
});

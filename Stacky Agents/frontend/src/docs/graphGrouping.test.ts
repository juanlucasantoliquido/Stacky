/**
 * graphGrouping.test.ts — Plan 268 F5.1. Tests PUROS de la agrupación y del colapso.
 */
import { describe, it, expect } from "vitest";
import {
  GROUP_NODE_PREFIX,
  groupKeyOf,
  groupLabelOf,
  groupKeysOf,
  assignGroupColorSlots,
  collapseGroups,
  isGroupNodeId,
  groupKeyFromNodeId,
} from "./graphGrouping";
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";

function node(id: string, overrides: Partial<DocGraphNode> = {}): DocGraphNode {
  return {
    id,
    kind: "note",
    label: id,
    path: `docs/${id}.md`,
    source_id: "s1",
    in_degree: 1,
    out_degree: 2,
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

describe("claves y etiquetas de grupo (plan 268 F5.1)", () => {
  it("groupKeyOf de una nota devuelve note: mas su source_id", () => {
    expect(groupKeyOf("note", "stacky")).toBe("note:stacky");
  });

  it("groupKeyOf de una nota sin source devuelve note:", () => {
    expect(groupKeyOf("note", "")).toBe("note:");
  });

  it("groupKeyOf de code y missing devuelve el kind pelado", () => {
    expect(groupKeyOf("code", "s1")).toBe("code");
    expect(groupKeyOf("missing", "s1")).toBe("missing");
  });

  it("groupLabelOf traduce note:stacky a una etiqueta legible", () => {
    expect(groupLabelOf("note:stacky")).toBe("Notas · stacky");
    expect(groupLabelOf("code")).toBe("Código");
    expect(groupLabelOf("missing")).toBe("Faltantes");
  });

  it("groupLabelOf de note: sin fuente dice sin fuente", () => {
    expect(groupLabelOf("note:")).toBe("Notas · (sin fuente)");
  });

  it("groupKeysOf ordena note:* por source y deja code y missing al final", () => {
    const g = graphOf([
      node("m", { kind: "missing", source_id: "" }),
      node("b", { source_id: "zeta" }),
      node("c", { kind: "code", source_id: "" }),
      node("a", { source_id: "alfa" }),
    ]);
    expect(groupKeysOf(g)).toEqual(["note:alfa", "note:zeta", "code", "missing"]);
  });

  it("groupKeysOf con grafo vacio devuelve lista vacia", () => {
    expect(groupKeysOf(graphOf([]))).toEqual([]);
    expect(groupKeysOf(undefined)).toEqual([]);
  });

  it("assignGroupColorSlots asigna slots consecutivos y estables", () => {
    const slots = assignGroupColorSlots(["note:a", "note:b", "code"]);
    expect(slots.get("note:a")).toBe(0);
    expect(slots.get("note:b")).toBe(1);
    expect(slots.get("code")).toBe(2);
    // una clave repetida no consume otro slot
    const dup = assignGroupColorSlots(["x", "x", "y"]);
    expect(dup.get("y")).toBe(1);
    expect(dup.size).toBe(2);
  });

  it("isGroupNodeId y groupKeyFromNodeId son inversas", () => {
    const id = GROUP_NODE_PREFIX + "note:stacky";
    expect(isGroupNodeId(id)).toBe(true);
    expect(groupKeyFromNodeId(id)).toBe("note:stacky");
    expect(isGroupNodeId("note-normal")).toBe(false);
    expect(groupKeyFromNodeId("note-normal")).toBeNull();
  });
});

describe("collapseGroups (plan 268 F5.1)", () => {
  it("collapseGroups con lista vacia devuelve el MISMO objeto", () => {
    const g = graphOf([node("a")]);
    expect(collapseGroups(g, [])).toBe(g);
  });

  it("collapseGroups reemplaza los miembros por un unico super-nodo", () => {
    const g = graphOf([
      node("a", { source_id: "s1" }),
      node("b", { source_id: "s1" }),
      node("z", { source_id: "s2" }),
    ]);
    const out = collapseGroups(g, ["note:s1"]);
    expect(out.nodes.map((n) => n.id)).toEqual([`${GROUP_NODE_PREFIX}note:s1`, "z"]);
    const sup = out.nodes[0];
    expect(sup.label).toBe("Notas · s1 (2)");
    expect(sup.path).toBe("");
    expect(sup.source_id).toBe("s1");
    expect(sup.kind).toBe("note");
  });

  it("el super-nodo suma los grados de sus miembros", () => {
    const g = graphOf([
      node("a", { in_degree: 3, out_degree: 1 }),
      node("b", { in_degree: 4, out_degree: 5 }),
    ]);
    const sup = collapseGroups(g, ["note:s1"]).nodes[0];
    expect(sup.in_degree).toBe(7);
    expect(sup.out_degree).toBe(6);
  });

  it("collapseGroups remapea las aristas al super-nodo", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("z", { source_id: "s2" })],
      [edge("a", "z")]
    );
    const out = collapseGroups(g, ["note:s1"]);
    expect(out.edges).toEqual([{ source: `${GROUP_NODE_PREFIX}note:s1`, target: "z", kind: "md" }]);
  });

  it("collapseGroups deduplica aristas iguales tras el remapeo", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("b", { source_id: "s1" }), node("z", { source_id: "s2" })],
      [edge("a", "z"), edge("b", "z")]
    );
    expect(collapseGroups(g, ["note:s1"]).edges.length).toBe(1);
  });

  it("collapseGroups descarta las aristas internas al grupo colapsado", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("b", { source_id: "s1" })],
      [edge("a", "b")]
    );
    expect(collapseGroups(g, ["note:s1"]).edges).toEqual([]);
  });

  it("collapseGroups de DOS grupos deja una arista entre los dos super-nodos", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("z", { source_id: "s2" })],
      [edge("a", "z")]
    );
    const out = collapseGroups(g, ["note:s1", "note:s2"]);
    expect(out.nodes.map((n) => n.id)).toEqual([
      `${GROUP_NODE_PREFIX}note:s1`,
      `${GROUP_NODE_PREFIX}note:s2`,
    ]);
    expect(out.edges.length).toBe(1);
    expect(out.edges[0].source).toBe(`${GROUP_NODE_PREFIX}note:s1`);
    expect(out.edges[0].target).toBe(`${GROUP_NODE_PREFIX}note:s2`);
  });

  it("collapseGroups de un grupo inexistente no cambia nada", () => {
    const g = graphOf([node("a", { source_id: "s1" })]);
    expect(collapseGroups(g, ["note:no-existe"])).toBe(g);
  });

  it("collapseGroups no muta el grafo de entrada", () => {
    const g = graphOf(
      [node("a", { source_id: "s1" }), node("z", { source_id: "s2" })],
      [edge("a", "z")],
      { orphans: ["a"] }
    );
    const snapshot = JSON.stringify(g);
    collapseGroups(g, ["note:s1"]);
    expect(JSON.stringify(g)).toBe(snapshot);
  });

  it("collapseGroups recorta orphans a los nodos vivos", () => {
    const g = graphOf([node("a", { source_id: "s1" }), node("z", { source_id: "s2" })], [], {
      orphans: ["a", "z"],
    });
    expect(collapseGroups(g, ["note:s1"]).orphans).toEqual(["z"]);
  });

  it("collapseGroups puede colapsar el grupo code", () => {
    const g = graphOf([
      node("c1", { kind: "code", source_id: "" }),
      node("c2", { kind: "code", source_id: "" }),
    ]);
    const out = collapseGroups(g, ["code"]);
    expect(out.nodes.length).toBe(1);
    expect(out.nodes[0].id).toBe(`${GROUP_NODE_PREFIX}code`);
    expect(out.nodes[0].kind).toBe("code");
    expect(out.nodes[0].label).toBe("Código (2)");
  });
});

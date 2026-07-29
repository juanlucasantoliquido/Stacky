/**
 * graphExplorerState.test.ts — Plan 268 F0.5.
 * Tests PUROS del reducer del explorador del grafo documental (sin React, sin DOM).
 */
import { describe, it, expect } from "vitest";
import {
  graphExplorerReducer,
  INITIAL_EXPLORER_STATE,
  EMPTY_FILTERS,
  type GraphExplorerState,
} from "./graphExplorerState";

function st(overrides: Partial<GraphExplorerState> = {}): GraphExplorerState {
  return { ...INITIAL_EXPLORER_STATE, ...overrides };
}

describe("graphExplorerReducer (plan 268 F0.5)", () => {
  it("SET_QUERY resetea matchIndex a 0", () => {
    const next = graphExplorerReducer(st({ matchIndex: 7 }), {
      type: "SET_QUERY",
      query: "plan",
    });
    expect(next.query).toBe("plan");
    expect(next.matchIndex).toBe(0);
  });

  it("NEXT_MATCH cicla 0->1->2->0 con total=3", () => {
    let s = st();
    s = graphExplorerReducer(s, { type: "NEXT_MATCH", total: 3 });
    expect(s.matchIndex).toBe(1);
    s = graphExplorerReducer(s, { type: "NEXT_MATCH", total: 3 });
    expect(s.matchIndex).toBe(2);
    s = graphExplorerReducer(s, { type: "NEXT_MATCH", total: 3 });
    expect(s.matchIndex).toBe(0);
  });

  it("PREV_MATCH desde 0 envuelve al ultimo", () => {
    const next = graphExplorerReducer(st({ matchIndex: 0 }), {
      type: "PREV_MATCH",
      total: 4,
    });
    expect(next.matchIndex).toBe(3);
  });

  it("NEXT_MATCH con total=0 deja matchIndex en 0", () => {
    const next = graphExplorerReducer(st({ matchIndex: 5 }), {
      type: "NEXT_MATCH",
      total: 0,
    });
    expect(next.matchIndex).toBe(0);
    const prev = graphExplorerReducer(st({ matchIndex: 5 }), {
      type: "PREV_MATCH",
      total: 0,
    });
    expect(prev.matchIndex).toBe(0);
  });

  it("TOGGLE_KIND agrega y saca el mismo kind", () => {
    let s = graphExplorerReducer(st(), { type: "TOGGLE_KIND", kind: "code" });
    expect(s.filters.kinds).toEqual(["code"]);
    s = graphExplorerReducer(s, { type: "TOGGLE_KIND", kind: "code" });
    expect(s.filters.kinds).toEqual([]);
  });

  it("TOGGLE_SOURCE mantiene la lista ordenada", () => {
    let s = graphExplorerReducer(st(), { type: "TOGGLE_SOURCE", sourceId: "zeta" });
    s = graphExplorerReducer(s, { type: "TOGGLE_SOURCE", sourceId: "alfa" });
    expect(s.filters.sourceIds).toEqual(["alfa", "zeta"]);
  });

  it("SET_MIN_DEGREE clampea negativos a 0", () => {
    expect(
      graphExplorerReducer(st(), { type: "SET_MIN_DEGREE", minDegree: -5 }).filters.minDegree
    ).toBe(0);
    expect(
      graphExplorerReducer(st(), { type: "SET_MIN_DEGREE", minDegree: 3.9 }).filters.minDegree
    ).toBe(3);
    expect(
      graphExplorerReducer(st(), { type: "SET_MIN_DEGREE", minDegree: NaN }).filters.minDegree
    ).toBe(0);
  });

  it("RESET_FILTERS vuelve a EMPTY_FILTERS sin tocar la query", () => {
    const dirty = st({
      query: "plan",
      filters: { ...EMPTY_FILTERS, hideOrphans: true, minDegree: 4, kinds: ["note"] },
    });
    const next = graphExplorerReducer(dirty, { type: "RESET_FILTERS" });
    expect(next.filters).toEqual(EMPTY_FILTERS);
    expect(next.query).toBe("plan");
  });

  it("TOGGLE_HIDE_ORPHANS y TOGGLE_ONLY_STALE alternan su bandera", () => {
    let s = graphExplorerReducer(st(), { type: "TOGGLE_HIDE_ORPHANS" });
    expect(s.filters.hideOrphans).toBe(true);
    s = graphExplorerReducer(s, { type: "TOGGLE_HIDE_ORPHANS" });
    expect(s.filters.hideOrphans).toBe(false);
    s = graphExplorerReducer(s, { type: "TOGGLE_ONLY_STALE" });
    expect(s.filters.onlyStale).toBe(true);
  });

  it("TOGGLE_EDGE_KIND agrega y saca el mismo tipo de arista", () => {
    let s = graphExplorerReducer(st(), { type: "TOGGLE_EDGE_KIND", edgeKind: "wikilink" });
    expect(s.filters.edgeKinds).toEqual(["wikilink"]);
    s = graphExplorerReducer(s, { type: "TOGGLE_EDGE_KIND", edgeKind: "wikilink" });
    expect(s.filters.edgeKinds).toEqual([]);
  });

  it("FOCUS_NODE apila la raiz anterior en focusHistory", () => {
    let s = graphExplorerReducer(st(), { type: "FOCUS_NODE", nodeId: "a" });
    expect(s.focusRootId).toBe("a");
    expect(s.focusHistory).toEqual([]);
    expect(s.peekNodeId).toBe("a");
    s = graphExplorerReducer(s, { type: "FOCUS_NODE", nodeId: "b" });
    expect(s.focusRootId).toBe("b");
    expect(s.focusHistory).toEqual(["a"]);
  });

  it("FOCUS_NODE sobre la misma raiz no duplica historial", () => {
    const s = graphExplorerReducer(st({ focusRootId: "a", focusHistory: ["z"] }), {
      type: "FOCUS_NODE",
      nodeId: "a",
    });
    expect(s.focusHistory).toEqual(["z"]);
  });

  it("FOCUS_BACK vuelve a la raiz anterior y desapila", () => {
    const s = graphExplorerReducer(st({ focusRootId: "c", focusHistory: ["a", "b"] }), {
      type: "FOCUS_BACK",
    });
    expect(s.focusRootId).toBe("b");
    expect(s.focusHistory).toEqual(["a"]);
    expect(s.peekNodeId).toBe("b");
  });

  it("FOCUS_BACK con historial vacio limpia el foco", () => {
    const s = graphExplorerReducer(st({ focusRootId: "c", focusHistory: [] }), {
      type: "FOCUS_BACK",
    });
    expect(s.focusRootId).toBeNull();
  });

  it("CLEAR_FOCUS limpia raiz e historial", () => {
    const s = graphExplorerReducer(st({ focusRootId: "c", focusHistory: ["a"] }), {
      type: "CLEAR_FOCUS",
    });
    expect(s.focusRootId).toBeNull();
    expect(s.focusHistory).toEqual([]);
  });

  it("SET_FOCUS_DEPTH clampea a [1,3]", () => {
    expect(graphExplorerReducer(st(), { type: "SET_FOCUS_DEPTH", depth: 0 }).focusDepth).toBe(1);
    expect(graphExplorerReducer(st(), { type: "SET_FOCUS_DEPTH", depth: 9 }).focusDepth).toBe(3);
    expect(graphExplorerReducer(st(), { type: "SET_FOCUS_DEPTH", depth: 2 }).focusDepth).toBe(2);
  });

  it("TOGGLE_GROUP_COLLAPSED agrega y saca la clave", () => {
    let s = graphExplorerReducer(st(), {
      type: "TOGGLE_GROUP_COLLAPSED",
      groupKey: "note:stacky",
    });
    expect(s.collapsedGroups).toEqual(["note:stacky"]);
    s = graphExplorerReducer(s, { type: "TOGGLE_GROUP_COLLAPSED", groupKey: "note:stacky" });
    expect(s.collapsedGroups).toEqual([]);
  });

  it("SET_PEEK con el mismo id devuelve el MISMO objeto", () => {
    const base = st({ peekNodeId: "a" });
    expect(graphExplorerReducer(base, { type: "SET_PEEK", nodeId: "a" })).toBe(base);
    expect(graphExplorerReducer(base, { type: "SET_PEEK", nodeId: null }).peekNodeId).toBeNull();
  });

  it("RESET_ALL vuelve al estado inicial", () => {
    const s = graphExplorerReducer(st({ query: "x", focusRootId: "a" }), { type: "RESET_ALL" });
    expect(s).toBe(INITIAL_EXPLORER_STATE);
  });

  it("accion desconocida devuelve el MISMO objeto de estado", () => {
    const base = st({ query: "hola" });
    const next = graphExplorerReducer(base, { type: "NO_EXISTE" } as never);
    expect(next).toBe(base);
  });
});

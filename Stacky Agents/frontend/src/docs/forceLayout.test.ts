import { describe, it, expect } from "vitest";
import {
  MAX_ANIMATED_NODES,
  nodeRadius,
  initLayout,
  stepLayout,
  staticLayout,
} from "./forceLayout";
import type { DocGraphResponse } from "./docGraphModel";

function baseGraph(overrides: Partial<DocGraphResponse> = {}): DocGraphResponse {
  return {
    ok: true,
    generated_at: "2026-07-09T00:00:00+00:00",
    active_project: "TEST",
    sources: [],
    nodes: [],
    edges: [],
    orphans: [],
    stats: {},
    doc_health: null,
    ...overrides,
  };
}

function note(id: string, inDeg = 0, kind: "note" | "code" | "missing" = "note") {
  return {
    id,
    kind,
    label: id,
    path: id + ".md",
    source_id: "s",
    in_degree: inDeg,
    out_degree: 0,
    has_frontmatter: false,
    exists: true,
  };
}

function graphWithN(n: number): DocGraphResponse {
  const nodes = Array.from({ length: n }, (_, i) => note("n" + i, i % 5));
  return baseGraph({ nodes });
}

describe("forceLayout", () => {
  it("nodeRadius_scales_and_caps", () => {
    expect(nodeRadius(0)).toBe(4);
    expect(nodeRadius(1)).toBeCloseTo(5.15, 5);
    expect(nodeRadius(1000)).toBe(15); // tope 4 + 11
  });

  it("initLayout_seeds_are_deterministic", () => {
    const g = graphWithN(20);
    const a = initLayout(g, 800, 600, false);
    const b = initLayout(g, 800, 600, false);
    expect(a.nodes.map((n) => [n.x, n.y])).toEqual(
      b.nodes.map((n) => [n.x, n.y])
    );
  });

  it("initLayout_disables_animation_over_threshold", () => {
    const g = graphWithN(MAX_ANIMATED_NODES + 1);
    const s = initLayout(g, 800, 600, false);
    expect(s.animated).toBe(false);
  });

  it("initLayout_disables_animation_when_reduced_motion", () => {
    const g = graphWithN(10);
    const s = initLayout(g, 800, 600, true);
    expect(s.animated).toBe(false);
  });

  it("stepLayout_reduces_energy_over_iterations", () => {
    const nodes = Array.from({ length: 15 }, (_, i) => note("n" + i, i % 3));
    const edges = nodes.slice(1).map((n) => ({
      source: "n0",
      target: n.id,
      kind: "md" as const,
    }));
    const g = baseGraph({ nodes, edges });
    const s = initLayout(g, 800, 600, false);
    const first = stepLayout(s);
    let last = first;
    for (let i = 0; i < 100; i++) last = stepLayout(s);
    expect(last).toBeLessThan(first);
  });

  it("stepLayout_keeps_nodes_in_bounds", () => {
    const g = graphWithN(30);
    const s = initLayout(g, 400, 300, false);
    for (let i = 0; i < 60; i++) stepLayout(s);
    for (const n of s.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(400);
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y).toBeLessThanOrEqual(300);
    }
  });

  it("staticLayout_is_deterministic_and_groups_columns", () => {
    const nodes = [
      note("a", 0, "note"),
      note("b", 0, "note"),
      note("c", 0, "code"),
      note("d", 0, "missing"),
    ];
    const g = baseGraph({ nodes });
    const s1 = initLayout(g, 800, 600, true);
    const s2 = initLayout(g, 800, 600, true);
    staticLayout(s1);
    staticLayout(s2);
    // determinístico
    expect(s1.nodes.map((n) => [n.x, n.y])).toEqual(
      s2.nodes.map((n) => [n.x, n.y])
    );
    // mismo grupo (note) → misma columna x; distinto grupo → distinta x
    const byId = Object.fromEntries(s1.nodes.map((n) => [n.id, n]));
    expect(byId["a"].x).toBe(byId["b"].x);
    expect(byId["a"].x).not.toBe(byId["c"].x);
    expect(byId["c"].x).not.toBe(byId["d"].x);
  });
});

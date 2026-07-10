import { describe, it, expect } from "vitest";
import {
  backlinksOf,
  filterNodeIds,
  type DocGraphResponse,
} from "./docGraphModel";

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

function note(id: string, path: string, label = path) {
  return {
    id,
    kind: "note" as const,
    label,
    path,
    source_id: "s",
    in_degree: 0,
    out_degree: 0,
    has_frontmatter: false,
    exists: true,
  };
}

describe("backlinksOf", () => {
  it("backlinksOf_returns_sources_targeting_node", () => {
    const g = baseGraph({
      nodes: [
        note("note:a", "a.md"),
        note("note:b", "b.md"),
        note("note:c", "c.md"),
      ],
      edges: [
        { source: "note:b", target: "note:a", kind: "wikilink" },
        { source: "note:c", target: "note:a", kind: "md" },
        { source: "note:a", target: "note:c", kind: "md" },
      ],
    });
    const res = backlinksOf(g, "note:a");
    expect(res.map((n) => n.id)).toEqual(["note:b", "note:c"]); // ordenado por path
  });

  it("backlinksOf_empty_when_no_incoming", () => {
    const g = baseGraph({
      nodes: [note("note:a", "a.md"), note("note:b", "b.md")],
      edges: [{ source: "note:a", target: "note:b", kind: "md" }],
    });
    expect(backlinksOf(g, "note:a")).toEqual([]);
  });

  it("backlinksOf_null_node_returns_empty", () => {
    const g = baseGraph({ nodes: [note("note:a", "a.md")] });
    expect(backlinksOf(g, null)).toEqual([]);
    expect(backlinksOf(undefined, "note:a")).toEqual([]);
  });
});

describe("filterNodeIds", () => {
  it("filterNodeIds_matches_substring_case_insensitive", () => {
    const g = baseGraph({
      nodes: [
        note("note:a", "Motor.md", "Motor.md"),
        note("note:b", "Agenda.md", "Agenda.md"),
        note("note:c", "motorcito.md", "motorcito.md"),
      ],
    });
    const res = filterNodeIds(g, "MOTOR");
    expect(res).toEqual(new Set(["note:a", "note:c"]));
  });

  it("filterNodeIds_empty_query_returns_empty_set", () => {
    const g = baseGraph({ nodes: [note("note:a", "Motor.md", "Motor.md")] });
    expect(filterNodeIds(g, "   ")).toEqual(new Set());
  });

  it("filterNodeIds_no_match_returns_empty_set", () => {
    const g = baseGraph({ nodes: [note("note:a", "Motor.md", "Motor.md")] });
    expect(filterNodeIds(g, "zzz")).toEqual(new Set());
  });
});

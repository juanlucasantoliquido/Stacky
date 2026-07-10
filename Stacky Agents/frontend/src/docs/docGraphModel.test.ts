import { describe, it, expect } from "vitest";
import { summarizeGraph, type DocGraphResponse } from "./docGraphModel";

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

function note(id: string, path: string, inDeg = 0, outDeg = 0) {
  return {
    id,
    kind: "note" as const,
    label: path.split("/").pop() ?? path,
    path,
    source_id: "project-docs:docs",
    in_degree: inDeg,
    out_degree: outDeg,
    has_frontmatter: false,
    exists: true,
  };
}

describe("summarizeGraph", () => {
  it("summarizes empty graph", () => {
    const s = summarizeGraph(baseGraph());
    expect(s.notes).toBe(0);
    expect(s.codeRefs).toBe(0);
    expect(s.missing).toBe(0);
    expect(s.totalEdges).toBe(0);
    expect(s.totalBacklinks).toBe(0);
    expect(s.orphanNotes).toEqual([]);
    expect(s.sources).toBe(0);
    expect(s.health).toBeNull();
  });

  it("counts backlinks as sum of note in_degree", () => {
    const s = summarizeGraph(
      baseGraph({
        nodes: [note("note:a", "a.md", 2), note("note:b", "b.md", 3)],
      })
    );
    expect(s.notes).toBe(2);
    expect(s.totalBacklinks).toBe(5);
  });

  it("orphan notes resolved from ids and sorted by path", () => {
    const s = summarizeGraph(
      baseGraph({
        nodes: [note("note:z", "z.md"), note("note:a", "a.md"), note("note:m", "m.md")],
        orphans: ["note:z", "note:a"],
      })
    );
    expect(s.orphanNotes.map((n) => n.path)).toEqual(["a.md", "z.md"]);
  });

  it("tolerates null doc_health", () => {
    const s = summarizeGraph(baseGraph({ doc_health: null }));
    expect(s.health).toBeNull();
  });

  it("missing and code nodes not counted as notes", () => {
    const s = summarizeGraph(
      baseGraph({
        nodes: [
          note("note:a", "a.md", 1),
          {
            id: "code:x.py",
            kind: "code",
            label: "x.py",
            path: "x.py",
            source_id: "",
            in_degree: 0,
            out_degree: 0,
            has_frontmatter: false,
            exists: true,
          },
          {
            id: "missing:foo",
            kind: "missing",
            label: "foo",
            path: "foo",
            source_id: "",
            in_degree: 0,
            out_degree: 0,
            has_frontmatter: false,
            exists: false,
          },
        ],
      })
    );
    expect(s.notes).toBe(1);
    expect(s.codeRefs).toBe(1);
    expect(s.missing).toBe(1);
  });
});

import { describe, it, expect } from "vitest";
import { noteIsStale, staleEdges } from "./staleness";
import { summarizeGraph } from "./docGraphModel";
import type { DocGraphResponse } from "./docGraphModel";

function baseGraph(): DocGraphResponse {
  return {
    ok: true,
    generated_at: "",
    active_project: null,
    sources: [],
    nodes: [],
    edges: [],
    orphans: [],
    stats: {},
    doc_health: null,
  };
}

describe("Plan 114 — staleness model", () => {
  it("noteIsStale_reads_has_stale", () => {
    expect(noteIsStale({ has_stale: true } as any)).toBe(true);
    expect(noteIsStale({ has_stale: false } as any)).toBe(false);
    expect(noteIsStale({} as any)).toBe(false); // ausente → false
    expect(noteIsStale(null)).toBe(false);
    expect(noteIsStale(undefined)).toBe(false);
  });

  it("staleEdges_filter", () => {
    const g = baseGraph();
    g.edges = [
      { source: "a", target: "code:x", kind: "code_ref", stale: true },
      { source: "a", target: "code:y", kind: "code_ref", stale: false },
      { source: "a", target: "code:z", kind: "code_ref" }, // sin campo
      { source: "a", target: "b", kind: "md", stale: true as any }, // no code_ref
    ];
    const out = staleEdges(g);
    expect(out).toHaveLength(1);
    expect(out[0].target).toBe("code:x");
    expect(staleEdges(undefined)).toEqual([]);
  });

  it("coverage_summary_includes_stale_notes_when_present", () => {
    const withStats = baseGraph();
    withStats.stale_stats = { stale_edges: 3, stale_notes: 2 };
    expect(summarizeGraph(withStats).staleNotes).toBe(2);

    const without = baseGraph();
    expect(summarizeGraph(without).staleNotes).toBeUndefined(); // flag OFF → sin lanzar
  });
});

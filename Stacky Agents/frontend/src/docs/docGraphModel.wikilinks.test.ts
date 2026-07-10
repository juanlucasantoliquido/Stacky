import { describe, it, expect } from "vitest";
import {
  buildNameIndex,
  resolveWikilink,
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

function note(
  id: string,
  path: string,
  label: string,
  sourceId = "project-docs:docs"
) {
  return {
    id,
    kind: "note" as const,
    label,
    path,
    source_id: sourceId,
    in_degree: 0,
    out_degree: 0,
    has_frontmatter: false,
    exists: true,
  };
}

describe("buildNameIndex / resolveWikilink", () => {
  it("buildNameIndex_maps_basename_lowercase", () => {
    const idx = buildNameIndex(
      baseGraph({
        nodes: [note("note:a", "sub/Nota Motor.md", "Nota Motor.md")],
      })
    );
    expect(idx.get("nota motor")).toBe("note:a");
    // Solo notas: código y missing no entran.
    expect(idx.size).toBe(1);
  });

  it("buildNameIndex_collision_lower_path_wins", () => {
    const idx = buildNameIndex(
      baseGraph({
        nodes: [
          note("note:z", "zeta/Guia.md", "Guia.md"),
          note("note:a", "alfa/Guia.md", "Guia.md"),
        ],
      })
    );
    // path "alfa/..." < "zeta/..." → gana note:a.
    expect(idx.get("guia")).toBe("note:a");
  });

  it("resolveWikilink_hits_and_misses", () => {
    const idx = buildNameIndex(
      baseGraph({ nodes: [note("note:a", "a/Nota.md", "Nota.md")] })
    );
    expect(resolveWikilink("wikilink:Nota", idx)).toBe("note:a");
    expect(resolveWikilink("wikilink:  nota  ", idx)).toBe("note:a");
    expect(resolveWikilink("wikilink:Inexistente", idx)).toBeNull();
    expect(resolveWikilink("http://x", idx)).toBeNull();
  });
});

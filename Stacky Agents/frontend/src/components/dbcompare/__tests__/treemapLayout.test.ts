import { describe, it, expect } from "vitest";
import { computeTreemapLayout, tableTreemapInputs, type TreemapInput, type TreemapRect } from "../treemapLayout";
import type { SchemaDiff, DiffItem } from "../dbcompareTypes";

function item(partial: Partial<DiffItem>): DiffItem {
  return {
    object_type: "table",
    schema: "dbo",
    name: "T",
    action: "changed",
    severity: "warn",
    changes: [],
    ...partial,
  };
}

function fixtureDiff(items: DiffItem[]): SchemaDiff {
  return {
    version: 1,
    engine: "sqlserver",
    source: { alias: "src", snapshot_id: "s1", content_hash: "h1" },
    target: { alias: "tgt", snapshot_id: "s2", content_hash: "h2" },
    items,
    summary: {
      by_severity: { danger: 0, warn: 0, info: 0 },
      by_action: { added: 0, removed: 0, changed: 0 },
      by_object_type: { table: 0, view: 0, sequence: 0 },
      objects_total: 0,
      objects_unchanged: 0,
      parity_score: 100,
    },
  };
}

function rectsOverlap(a: TreemapRect, b: TreemapRect, tol: number): boolean {
  const xOverlap = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const yOverlap = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return xOverlap > tol && yOverlap > tol;
}

describe("Plan 124 F4 — treemapLayout (pure)", () => {
  const sevenItems: TreemapInput[] = [
    { key: "t1", label: "t1", weight: 12, state: "unchanged" },
    { key: "t2", label: "t2", weight: 9, state: "changed" },
    { key: "t3", label: "t3", weight: 7, state: "added" },
    { key: "t4", label: "t4", weight: 6, state: "removed" },
    { key: "t5", label: "t5", weight: 4, state: "unchanged" },
    { key: "t6", label: "t6", weight: 3, state: "changed" },
    { key: "t7", label: "t7", weight: 1, state: "unchanged" },
  ];

  it("test determinismo: mismo input dos veces -> deepEqual", () => {
    const out1 = computeTreemapLayout(sevenItems, 1000, 560);
    const out2 = computeTreemapLayout(sevenItems, 1000, 560);
    expect(out1).toEqual(out2);
  });

  it("test sin solapes: ningún par de rects se intersecta (tolerancia 0.01)", () => {
    const rects = computeTreemapLayout(sevenItems, 1000, 560);
    expect(rects).toHaveLength(7);
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        expect(rectsOverlap(rects[i], rects[j], 0.01)).toBe(false);
      }
    }
  });

  it("test cubre area: suma de áreas ≈ width*height ± 0.5", () => {
    const width = 1000;
    const height = 560;
    const rects = computeTreemapLayout(sevenItems, width, height);
    const totalArea = rects.reduce((s, r) => s + r.w * r.h, 0);
    expect(Math.abs(totalArea - width * height)).toBeLessThanOrEqual(0.5);
  });

  it("test orden y corte: pesos [8,3,2,1] -> primer split separa {8} | {3,2,1}", () => {
    const items: TreemapInput[] = [
      { key: "a", label: "a", weight: 8, state: "unchanged" },
      { key: "b", label: "b", weight: 3, state: "unchanged" },
      { key: "c", label: "c", weight: 2, state: "unchanged" },
      { key: "d", label: "d", weight: 1, state: "unchanged" },
    ];
    const width = 100;
    const rects = computeTreemapLayout(items, width, 50);
    const a = rects.find((r) => r.key === "a")!;
    // {8} ocupa la franja izquierda de ancho width*8/14 (w>=h, corte vertical)
    expect(a.x).toBe(0);
    expect(a.w).toBeCloseTo((width * 8) / 14, 1);
  });

  it("test corte balanceado [FIX C4]: pesos [5,5,4] -> split separa {5} | {5,4} (diff 4, no {5,5}|{4} diff 6)", () => {
    const items: TreemapInput[] = [
      { key: "a", label: "a", weight: 5, state: "unchanged" },
      { key: "b", label: "b", weight: 5, state: "unchanged" },
      { key: "c", label: "c", weight: 4, state: "unchanged" },
    ];
    const width = 140;
    const rects = computeTreemapLayout(items, width, 50);
    const a = rects.find((r) => r.key === "a")!;
    // "a" solo (peso 5) debe ocupar una franja de ancho width*5/14 = 50, NO width*10/14
    expect(a.w).toBeCloseTo((width * 5) / 14, 1);
  });

  it("test items vacios [FIX C7]: computeTreemapLayout([]) -> []", () => {
    expect(computeTreemapLayout([], 1000, 560)).toEqual([]);
  });

  describe("tableTreemapInputs", () => {
    it("states y weights exactos, orden alfabético de key", () => {
      const diff = fixtureDiff([
        item({ schema: "dbo", name: "CLIENTES", action: "changed" }),
        item({ schema: "dbo", name: "FAX", action: "removed" }),
      ]);
      const counts = { "dbo.CLIENTES": 12, "dbo.PRODUCTOS": 5 };
      const out = tableTreemapInputs(diff, counts);
      expect(out).toEqual([
        { key: "dbo.CLIENTES", label: "dbo.CLIENTES", weight: 12, state: "changed" },
        { key: "dbo.FAX", label: "dbo.FAX", weight: 1, state: "removed" },
        { key: "dbo.PRODUCTOS", label: "dbo.PRODUCTOS", weight: 5, state: "unchanged" },
      ]);
    });

    it("fallback mapa vacío -> weight 1", () => {
      const diff = fixtureDiff([item({ schema: "dbo", name: "CLIENTES", action: "changed" })]);
      const out = tableTreemapInputs(diff, {});
      expect(out).toEqual([{ key: "dbo.CLIENTES", label: "dbo.CLIENTES", weight: 1, state: "changed" }]);
    });

    it("ignora items que no son tablas (view/sequence)", () => {
      const diff = fixtureDiff([item({ object_type: "view", schema: "dbo", name: "V1", action: "added" })]);
      const out = tableTreemapInputs(diff, {});
      expect(out).toEqual([]);
    });
  });
});

/**
 * Tests de dirTreeModel.ts - Plan 107 F3
 * TDD: nesting determinístico de PlanEntry[] a árbol jerárquico (sin React).
 */
import { describe, it, expect } from "vitest";
import { buildDirTree, rollupCounts } from "./dirTreeModel";
import type { PlanEntry } from "./environmentModel";

function entry(path: string, status: PlanEntry["status"]): PlanEntry {
  return { path, status, reason: null };
}

describe("dirTreeModel", () => {
  it("nests two-level paths", () => {
    const tree = buildDirTree([entry("a", "to_create"), entry("a/b", "to_create")]);
    expect(tree).toHaveLength(1);
    expect(tree[0].name).toBe("a");
    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].name).toBe("b");
    expect(tree[0].children[0].path).toBe("a/b");
  });

  it("intermediate node without own entry", () => {
    const tree = buildDirTree([entry("x/y", "to_create")]);
    expect(tree).toHaveLength(1);
    const x = tree[0];
    expect(x.name).toBe("x");
    expect(x.selfStatus).toBeNull();
    expect(x.children).toHaveLength(1);
    expect(x.children[0].name).toBe("y");
    // status derivado de 'y' (único descendiente, to_create puro)
    expect(x.status).toBe("to_create");
  });

  it("rollup danger dominates", () => {
    const tree = buildDirTree([
      entry("a/ok", "to_create"),
      entry("a/bad", "conflict"),
    ]);
    const a = tree[0];
    expect(a.status).toBe("mixed");
  });

  it("rollup all to_create", () => {
    const tree = buildDirTree([
      entry("a/one", "to_create"),
      entry("a/two", "to_create"),
    ]);
    expect(tree[0].status).toBe("to_create");
  });

  it("counts only real entries", () => {
    const tree = buildDirTree([entry("x/y/z", "to_create")]);
    const x = tree[0];
    // x e y son intermedios (sin entry propio): solo 'z' cuenta.
    expect(x.counts).toEqual({ to_create: 1, exists_ok: 0, conflict: 0, unsafe: 0 });
    expect(x.children[0].counts).toEqual({ to_create: 1, exists_ok: 0, conflict: 0, unsafe: 0 });
  });

  it("backslash paths normalized", () => {
    const tree = buildDirTree([entry("a\\b", "to_create")]);
    expect(tree).toHaveLength(1);
    expect(tree[0].name).toBe("a");
    expect(tree[0].children[0].name).toBe("b");
    expect(tree[0].children[0].path).toBe("a/b");
  });

  it("deterministic order", () => {
    const tree = buildDirTree([
      entry("zeta", "to_create"),
      entry("alpha", "to_create"),
      entry("mid", "to_create"),
    ]);
    expect(tree.map((n) => n.name)).toEqual(["alpha", "mid", "zeta"]);
  });

  it("rollupCounts sums root nodes", () => {
    const tree = buildDirTree([
      entry("a", "to_create"),
      entry("b", "exists_ok"),
      entry("c", "conflict"),
    ]);
    expect(rollupCounts(tree)).toEqual({ to_create: 1, exists_ok: 1, conflict: 1, unsafe: 0 });
  });

  it("duplicate path keeps last selfStatus deterministically", () => {
    const tree = buildDirTree([entry("a", "to_create"), entry("a", "exists_ok")]);
    expect(tree).toHaveLength(1);
    expect(tree[0].selfStatus).toBe("exists_ok");
    expect(tree[0].counts).toEqual({ to_create: 0, exists_ok: 1, conflict: 0, unsafe: 0 });
  });
});

import { describe, it, expect } from "vitest";
import { buildColumnRows, buildSectionRows } from "../sideBySide";
import type { DiffItem, TableSnapshot, ColumnInfo } from "../dbcompareTypes";

function col(partial: Partial<ColumnInfo>): ColumnInfo {
  return { name: "c", type: "INT", nullable: false, default: null, autoincrement: false, ...partial };
}

function table(columns: ColumnInfo[]): TableSnapshot {
  return { columns, primary_key: { name: null, columns: [] }, foreign_keys: [], indexes: [], unique_constraints: [], check_constraints: [] };
}

function changedItem(): DiffItem {
  return { object_type: "table", schema: "dbo", name: "CLIENTES", action: "changed", severity: "danger", changes: [] };
}

function addedItem(): DiffItem {
  return { object_type: "table", schema: "dbo", name: "CLIENTES", action: "added", severity: "warn", changes: [] };
}

describe("Plan 124 F5 — sideBySide (pure)", () => {
  it("columna added + removed + type-changed: states y changedFields exactos, orden de filas", () => {
    const source = table([
      col({ name: "ID", type: "INT", autoincrement: true }),
      col({ name: "NOMBRE", type: "VARCHAR(50)" }),
      col({ name: "FAX", type: "VARCHAR(20)", nullable: true }),
    ]);
    const target = table([
      col({ name: "ID", type: "INT", autoincrement: true }),
      col({ name: "NOMBRE", type: "NVARCHAR(50)" }),
      col({ name: "DIRECCION", type: "VARCHAR(100)", nullable: true }),
    ]);
    const rows = buildColumnRows(changedItem(), source, target);
    expect(rows.map((r) => r.name)).toEqual(["ID", "NOMBRE", "FAX", "DIRECCION"]);

    expect(rows[0]).toMatchObject({ name: "ID", state: "unchanged", changedFields: [] });
    expect(rows[1]).toMatchObject({ name: "NOMBRE", state: "changed", changedFields: ["type"] });
    expect(rows[2]).toMatchObject({ name: "FAX", state: "added", changedFields: [] });
    expect(rows[2].target).toBeNull();
    expect(rows[3]).toMatchObject({ name: "DIRECCION", state: "removed", changedFields: [] });
    expect(rows[3].source).toBeNull();
  });

  it("tabla added con target null: todas las filas added", () => {
    const source = table([col({ name: "A" }), col({ name: "B" })]);
    const rows = buildColumnRows(addedItem(), source, null);
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.state === "added")).toBe(true);
    expect(rows.every((r) => r.target === null)).toBe(true);
  });

  it("tabla removed con source null: todas las filas removed", () => {
    const target = table([col({ name: "A" }), col({ name: "B" })]);
    const rows = buildColumnRows(changedItem(), null, target);
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.state === "removed")).toBe(true);
    expect(rows.every((r) => r.source === null)).toBe(true);
  });

  it("buildSectionRows genérico: source-only=added, match=unchanged, target-only=removed, orden preservado", () => {
    const sourceList = [{ id: "a" }, { id: "b" }];
    const targetList = [{ id: "b" }, { id: "c" }];
    const rows = buildSectionRows(sourceList, targetList, (x) => x.id);
    expect(rows.map((r) => r.key)).toEqual(["a", "b", "c"]);
    expect(rows[0]).toMatchObject({ key: "a", state: "added" });
    expect(rows[0].target).toBeNull();
    expect(rows[1]).toMatchObject({ key: "b", state: "unchanged" });
    expect(rows[2]).toMatchObject({ key: "c", state: "removed" });
    expect(rows[2].source).toBeNull();
  });
});

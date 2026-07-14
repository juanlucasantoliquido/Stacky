import { describe, it, expect } from "vitest";
import { buildSnapshotCounts } from "../snapshotCounts";
import type { DbSnapshot, TableSnapshot } from "../dbcompareTypes";

function table(nCols: number): TableSnapshot {
  return {
    columns: Array.from({ length: nCols }, (_, i) => ({
      name: `c${i}`,
      type: "INT",
      nullable: false,
      default: null,
      autoincrement: false,
    })),
    primary_key: { name: null, columns: [] },
    foreign_keys: [],
    indexes: [],
    unique_constraints: [],
    check_constraints: [],
  };
}

function snapshot(tables: Record<string, TableSnapshot>): DbSnapshot {
  return {
    version: 1,
    id: "s1",
    alias: "a",
    engine: "sqlserver",
    taken_at: "2026-07-14T00:00:00Z",
    duration_ms: 0,
    schemas: { dbo: { tables, views: {}, sequences: [] } },
    counts: { tables: Object.keys(tables).length, views: 0, sequences: 0, columns: 0 },
    content_hash: "h",
  };
}

describe("Plan 124 [integración F4] — snapshotCounts (pure)", () => {
  it("ambos snapshots null -> mapa vacío", () => {
    expect(buildSnapshotCounts(null, null)).toEqual({});
  });

  it("tabla en ambos lados -> usa el conteo del ORIGEN", () => {
    const source = snapshot({ CLIENTES: table(5) });
    const target = snapshot({ CLIENTES: table(9) });
    expect(buildSnapshotCounts(source, target)).toEqual({ "dbo.CLIENTES": 5 });
  });

  it("tabla solo en destino -> fallback al conteo del DESTINO", () => {
    const source = snapshot({});
    const target = snapshot({ FAX: table(3) });
    expect(buildSnapshotCounts(source, target)).toEqual({ "dbo.FAX": 3 });
  });

  it("tabla solo en origen -> usa el conteo del origen", () => {
    const source = snapshot({ NUEVA: table(7) });
    const target = snapshot({});
    expect(buildSnapshotCounts(source, target)).toEqual({ "dbo.NUEVA": 7 });
  });

  it("source null, target presente -> usa target completo", () => {
    const target = snapshot({ SOLO_TARGET: table(2) });
    expect(buildSnapshotCounts(null, target)).toEqual({ "dbo.SOLO_TARGET": 2 });
  });
});

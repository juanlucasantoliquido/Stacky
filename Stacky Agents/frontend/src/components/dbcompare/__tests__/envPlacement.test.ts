// Plan 157 F5 — tests puros de ubicación de la gestión de ambientes (vitest).
import { describe, it, expect } from "vitest";
import { shouldNudgeAddMore, shouldShowEmptyCta } from "../envPlacementLogic";
import type { DbEnvironment } from "../dbcompareTypes";

const mkEnv = (alias: string): DbEnvironment => ({
  alias,
  engine: "sqlserver",
  host: "h",
  port: 1433,
  database: "d",
  username: "u",
  odbc_driver: "",
  schema_filter: null,
  notes: "",
  created_at: "",
  last_used_at: null,
  has_password: false,
  latest_snapshot_taken_at: null,
  latest_snapshot_hash8: null,
});

describe("shouldShowEmptyCta", () => {
  it("true si flag ON y 0 ambientes", () => {
    expect(shouldShowEmptyCta([], true)).toBe(true);
  });
  it("false si flag OFF (aunque no haya ambientes)", () => {
    expect(shouldShowEmptyCta([], false)).toBe(false);
  });
  it("false si ya hay ambientes", () => {
    expect(shouldShowEmptyCta([mkEnv("a")], true)).toBe(false);
  });
});

describe("shouldNudgeAddMore", () => {
  it("true con exactamente 1 ambiente", () => {
    expect(shouldNudgeAddMore([mkEnv("a")])).toBe(true);
  });
  it("false con 0 ambientes", () => {
    expect(shouldNudgeAddMore([])).toBe(false);
  });
  it("false con 2 o más ambientes", () => {
    expect(shouldNudgeAddMore([mkEnv("a"), mkEnv("b")])).toBe(false);
  });
});

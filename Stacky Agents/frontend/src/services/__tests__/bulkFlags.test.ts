// Plan 187 F0 (K6) — parser puro de STACKY_BULK_ACTIONS_ENABLED.
// bulkFlags.ts es un WRAPPER sobre flagGate (197 §6.1): resolveBulkActionsEnabled
// delega en flagEnabledFrom con la key del 187. Estos 5 casos NO cambian (C6).
import { describe, it, expect } from "vitest";
import { resolveBulkActionsEnabled } from "../bulkFlags";

const KEY = "STACKY_BULK_ACTIONS_ENABLED";

describe("resolveBulkActionsEnabled (parser puro K6)", () => {
  it("off_cuando_value_false_literal", () => {
    expect(resolveBulkActionsEnabled([{ key: KEY, value: false }])).toBe(false);
  });

  it("on_cuando_value_true", () => {
    expect(resolveBulkActionsEnabled([{ key: KEY, value: true }])).toBe(true);
  });

  it("on_cuando_key_ausente", () => {
    expect(
      resolveBulkActionsEnabled([{ key: "OTRA_FLAG", value: false }]),
    ).toBe(true);
  });

  it("on_cuando_flags_undefined_o_null", () => {
    expect(resolveBulkActionsEnabled(undefined)).toBe(true);
    expect(resolveBulkActionsEnabled(null)).toBe(true);
  });

  it("on_cuando_value_string_false", () => {
    // SOLO el booleano literal apaga; el string "false" NO.
    expect(resolveBulkActionsEnabled([{ key: KEY, value: "false" }])).toBe(true);
  });
});

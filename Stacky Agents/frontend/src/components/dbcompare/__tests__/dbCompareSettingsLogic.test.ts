import { describe, expect, it } from "vitest";
import {
  DB_COMPARE_SETTINGS_KEYS,
  pickDbCompareSettings,
  validateIntSetting,
} from "../dbCompareSettingsLogic";
import type { HarnessFlagView } from "../../../api/endpoints";

function makeFlag(overrides: Partial<HarnessFlagView>): HarnessFlagView {
  return {
    key: "SOME_KEY",
    type: "bool",
    label: "label",
    description: "desc",
    group: "global",
    pair: null,
    env_only: false,
    value: true,
    category: "comparador_bd",
    default: true,
    default_known: true,
    active: true,
    requires: null,
    requires_met: true,
    min_value: null,
    max_value: null,
    in_bounds: true,
    ...overrides,
  };
}

describe("pickDbCompareSettings", () => {
  it("filtra y ordena las 4 flags en el orden declarado", () => {
    const flags = [
      makeFlag({ key: "STACKY_DB_COMPARE_DATA_MAX_ROWS", type: "int", value: 5000 }),
      makeFlag({ key: "STACKY_UNRELATED_ENABLED" }),
      makeFlag({ key: "STACKY_DB_COMPARE_ENABLED" }),
      makeFlag({ key: "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC", type: "int", value: 10 }),
      makeFlag({ key: "STACKY_DB_COMPARE_DATA_DIFF_ENABLED" }),
    ];
    const picked = pickDbCompareSettings(flags);
    expect(picked.map((f) => f.key)).toEqual([...DB_COMPARE_SETTINGS_KEYS]);
  });

  it("omite flags ausentes del registry sin romper", () => {
    const flags = [makeFlag({ key: "STACKY_DB_COMPARE_ENABLED" })];
    const picked = pickDbCompareSettings(flags);
    expect(picked.map((f) => f.key)).toEqual(["STACKY_DB_COMPARE_ENABLED"]);
  });

  it("lista vacía si no hay ninguna flag de DB Compare", () => {
    expect(pickDbCompareSettings([makeFlag({ key: "OTRA" })])).toEqual([]);
  });
});

describe("validateIntSetting", () => {
  it("acepta un entero dentro de bounds", () => {
    expect(validateIntSetting("60", 1, 120)).toEqual({ ok: true, value: 60 });
  });

  it("rechaza vacío", () => {
    const r = validateIntSetting("", 1, 120);
    expect(r.ok).toBe(false);
    expect(r.error).toBeTruthy();
  });

  it("rechaza no-entero", () => {
    const r = validateIntSetting("12.5", 1, 120);
    expect(r.ok).toBe(false);
  });

  it("rechaza por debajo del mínimo", () => {
    const r = validateIntSetting("0", 1, 120);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Mínimo/);
  });

  it("rechaza por encima del máximo", () => {
    const r = validateIntSetting("121", 1, 120);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Máximo/);
  });

  it("sin bounds declarados (null/null) acepta cualquier entero", () => {
    expect(validateIntSetting("999999", null, null)).toEqual({ ok: true, value: 999999 });
  });

  it("bounds del Comparador de BD reales: timeout 1-120", () => {
    expect(validateIntSetting("121", 1, 120).ok).toBe(false);
    expect(validateIntSetting("1", 1, 120).ok).toBe(true);
    expect(validateIntSetting("120", 1, 120).ok).toBe(true);
  });

  it("bounds del Comparador de BD reales: max_rows 100-200000", () => {
    expect(validateIntSetting("99", 100, 200000).ok).toBe(false);
    expect(validateIntSetting("200001", 100, 200000).ok).toBe(false);
    expect(validateIntSetting("5000", 100, 200000).ok).toBe(true);
  });
});

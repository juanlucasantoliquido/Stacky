import { describe, it, expect } from "vitest";
import { DEFAULT_OPEN_PR, shouldShowOpenPrCheckbox } from "./incidentDevPrModel";

describe("incidentDevPrModel", () => {
  it("DEFAULT_OPEN_PR es true (premarcado)", () => {
    expect(DEFAULT_OPEN_PR).toBe(true);
  });

  it("muestra el checkbox cuando canResolve && devPrEnabled", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: true, devPrEnabled: true })).toBe(true);
  });

  it("oculta el checkbox si devPrEnabled es false", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: true, devPrEnabled: false })).toBe(false);
  });

  it("oculta el checkbox si canResolve es false", () => {
    expect(shouldShowOpenPrCheckbox({ canResolve: false, devPrEnabled: true })).toBe(false);
  });
});

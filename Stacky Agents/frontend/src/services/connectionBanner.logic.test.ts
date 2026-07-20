import { describe, it, expect } from "vitest";
import { computeBannerView, freshnessLabel } from "./connectionBanner.logic";
import type { ConnectionSnapshot } from "./connectionMonitor";

function snap(p: Partial<ConnectionSnapshot>): ConnectionSnapshot {
  return {
    status: "healthy",
    attempt: 0,
    downSince: null,
    lastOkAt: null,
    lastRecoveredAt: null,
    enabled: true,
    ...p,
  };
}

describe("computeBannerView (Plan 192 F3)", () => {
  it("healthy => no visible", () => {
    expect(computeBannerView(snap({ status: "healthy" })).visible).toBe(false);
  });

  it("suspect => no visible (anti falso-positivo)", () => {
    expect(computeBannerView(snap({ status: "suspect" })).visible).toBe(false);
  });

  it("down attempt 0 => visible, kind down, mensaje exacto, attemptText null, showRetry", () => {
    const v = computeBannerView(snap({ status: "down", attempt: 0 }));
    expect(v.visible).toBe(true);
    expect(v.kind).toBe("down");
    expect(v.message).toBe("Sin conexión con el backend — reintentando…");
    expect(v.attemptText).toBeNull();
    expect(v.showRetry).toBe(true);
  });

  it("down attempt 3 => attemptText exacto '(intento 3)'", () => {
    const v = computeBannerView(snap({ status: "down", attempt: 3 }));
    expect(v.attemptText).toBe("(intento 3)");
  });

  it("recovering => visible, kind recovering, mensaje exacto, sin retry", () => {
    const v = computeBannerView(snap({ status: "recovering" }));
    expect(v.visible).toBe(true);
    expect(v.kind).toBe("recovering");
    expect(v.message).toBe("Backend de vuelta — actualizando…");
    expect(v.attemptText).toBeNull();
    expect(v.showRetry).toBe(false);
  });

  it("enabled:false + down => no visible (defensa en profundidad)", () => {
    expect(computeBannerView(snap({ enabled: false, status: "down" })).visible).toBe(false);
  });
});

describe("freshnessLabel (Plan 192 F3/F6)", () => {
  it("lastOkAt null => 'Sin respuesta del backend aún'", () => {
    expect(freshnessLabel(null, 10000)).toBe("Sin respuesta del backend aún");
  });

  it("hace 7s (redondeo a segundos con Math.round)", () => {
    expect(freshnessLabel(10000 - 7000, 10000)).toBe("Última respuesta del backend hace 7s");
  });

  it("redondea con Math.round (6600ms => 7s)", () => {
    expect(freshnessLabel(10000 - 6600, 10000)).toBe("Última respuesta del backend hace 7s");
  });
});

/** Plan 210 F7 — Modelo puro del veredicto de build. */
import { describe, expect, it } from "vitest";

import {
  orderedFindings,
  readBuildVerdict,
  verdictBadge,
  verdictColor,
  verdictLabel,
  type DevBuildVerdictSummary,
} from "./devBuildModel";

const v = (over: Partial<DevBuildVerdictSummary> = {}): DevBuildVerdictSummary => ({
  gate_ok: true,
  reason: "ok",
  entry_kind: "sln",
  solution: "App.sln",
  blocking_findings: [],
  warnings: [],
  ...over,
});

describe("verdictColor", () => {
  it("verde solo con gate_ok", () => expect(verdictColor(v())).toBe("green"));
  it("rojo si no pasó", () =>
    expect(verdictColor(v({ gate_ok: false, reason: "build_failed" }))).toBe("red"));
  it("gris si no hay veredicto", () => expect(verdictColor(null)).toBe("gray"));
});

describe("verdictLabel", () => {
  it("traduce las razones conocidas", () => {
    expect(verdictLabel("no_sln")).toContain(".sln");
    expect(verdictLabel("toolchain_missing")).toContain(".NET");
    expect(verdictLabel("build_failed")).toContain("errores");
    expect(verdictLabel("not_verified")).toContain("Ninguna máquina");
  });
  it("una razón desconocida se muestra tal cual", () => {
    expect(verdictLabel("razon_rara")).toBe("razon_rara");
  });
});

describe("verdictBadge", () => {
  it("verificado", () => {
    expect(verdictBadge(v())).toEqual({
      text: "Build verificado por máquina",
      color: "green",
    });
  });
  it("no verificado incluye la razón", () => {
    const badge = verdictBadge(v({ gate_ok: false, reason: "no_sln" }));
    expect(badge.color).toBe("red");
    expect(badge.text).toContain(".sln");
  });
  it("sin veredicto", () => {
    expect(verdictBadge(undefined)).toEqual({ text: "Build sin verificar", color: "gray" });
  });
});

describe("orderedFindings", () => {
  it("bloqueantes primero", () => {
    const out = orderedFindings(
      v({
        blocking_findings: [{ kind: "b", severity: "blocking", file: "x", detail: "d" }],
        warnings: [{ kind: "w", severity: "warning", file: "y", detail: "d" }],
      }),
    );
    expect(out.map((f) => f.kind)).toEqual(["b", "w"]);
  });
  it("sin veredicto es lista vacía", () => expect(orderedFindings(null)).toEqual([]));
});

describe("readBuildVerdict", () => {
  it("null si no hay metadata", () => {
    expect(readBuildVerdict(undefined)).toBeNull();
    expect(readBuildVerdict({})).toBeNull();
  });
  it("null si el shape es inválido", () => {
    expect(readBuildVerdict({ build_verdict: "texto" })).toBeNull();
    expect(readBuildVerdict({ build_verdict: { reason: "ok" } })).toBeNull();
  });
  it("normaliza un resumen válido", () => {
    const out = readBuildVerdict({
      build_verdict: { gate_ok: false, reason: "build_failed", solution: "A.sln" },
    });
    expect(out?.gate_ok).toBe(false);
    expect(out?.reason).toBe("build_failed");
    expect(out?.blocking_findings).toEqual([]);
  });
});

/** Plan 211 F5 — Modelo puro de los hallazgos. */
import { describe, expect, it } from "vitest";

import {
  countBlocking,
  findingLabel,
  findingsFromVerdict,
  groupBySeverity,
  paneColor,
  severityColor,
} from "./portFindingsModel";
import type { DevBuildFinding, DevBuildVerdictSummary } from "./devBuildModel";

const f = (severity: DevBuildFinding["severity"], kind = "server"): DevBuildFinding => ({
  kind,
  severity,
  file: "web.config",
  detail: `token de otro cliente (${kind})`,
});

describe("findingLabel", () => {
  it("traduce los kinds conocidos", () => {
    expect(findingLabel("post_build_event")).toBe("Evento post-build");
    expect(findingLabel("foreign_output_path")).toBe("Salida hacia otro cliente");
    expect(findingLabel("server")).toBe("Servidor de otro cliente");
  });
  it("un kind desconocido se muestra tal cual", () => {
    expect(findingLabel("raro")).toBe("raro");
  });
});

describe("severityColor", () => {
  it("mapea las severidades", () => {
    expect(severityColor("blocking")).toBe("red");
    expect(severityColor("warning")).toBe("amber");
    expect(severityColor("otra")).toBe("gray");
  });
});

describe("groupBySeverity", () => {
  it("separa bloqueantes de avisos", () => {
    const out = groupBySeverity([f("blocking"), f("warning"), f("blocking")]);
    expect(out.blocking).toHaveLength(2);
    expect(out.warning).toHaveLength(1);
  });
  it("lista vacía", () => {
    expect(groupBySeverity([])).toEqual({ blocking: [], warning: [] });
  });
});

describe("countBlocking", () => {
  it("cuenta solo los bloqueantes", () => {
    expect(countBlocking([f("blocking"), f("warning")])).toBe(1);
    expect(countBlocking([])).toBe(0);
  });
});

describe("findingsFromVerdict", () => {
  const v = (over: Partial<DevBuildVerdictSummary> = {}): DevBuildVerdictSummary => ({
    gate_ok: false,
    reason: "build_failed",
    entry_kind: "sln",
    solution: "App.sln",
    blocking_findings: [],
    warnings: [],
    ...over,
  });

  it("bloqueantes primero", () => {
    const out = findingsFromVerdict(
      v({ blocking_findings: [f("blocking", "path")], warnings: [f("warning", "product")] }),
    );
    expect(out.map((x) => x.kind)).toEqual(["path", "product"]);
  });
  it("sin veredicto es lista vacía", () => {
    expect(findingsFromVerdict(null)).toEqual([]);
  });
});

describe("paneColor", () => {
  it("rojo con algún bloqueante", () => {
    expect(paneColor([f("warning"), f("blocking")])).toBe("red");
  });
  it("ámbar con solo avisos", () => expect(paneColor([f("warning")])).toBe("amber"));
  it("gris sin items", () => expect(paneColor([])).toBe("gray"));
});

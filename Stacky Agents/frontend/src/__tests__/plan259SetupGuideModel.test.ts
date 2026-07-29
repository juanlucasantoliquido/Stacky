/**
 * Plan 259 F6 — Logica pura del panel de la guia de configuracion.
 * Sin React y sin red: RTL/jsdom no estan instalados en este repo.
 */
import { describe, it, expect } from "vitest";
import {
  GITLAB_FALLBACK_GUIDE,
  canVerify,
  isServerGuide,
  stepsToHighlight,
  summarizeChecks,
  type GuideCheckResult,
  type SetupGuideDoc,
} from "../projects/setupGuideModel";

function ok(id: string): GuideCheckResult {
  return { id, status: "ok", message: "" };
}
function fail(id: string): GuideCheckResult {
  return { id, status: "fail", message: "" };
}
function unknown(id: string): GuideCheckResult {
  return { id, status: "unknown", message: "" };
}

const GUIDE: SetupGuideDoc = {
  provider: "gitlab",
  display_name: "GitLab",
  summary: "resumen",
  required_fields: ["gitlab_url"],
  steps: [
    { id: "gl-01-instancia", title: "1", detail: "d", where: "gitlab" },
    { id: "gl-02-token", title: "2", detail: "d", where: "gitlab" },
    { id: "gl-04-project-path", title: "4", detail: "d", where: "gitlab" },
  ],
  checks: [
    { id: "chk-instancia", title: "i", fixes_step: "gl-01-instancia" },
    { id: "chk-token", title: "t", fixes_step: "gl-02-token" },
    { id: "chk-proyecto", title: "p", fixes_step: "gl-04-project-path" },
  ],
};

describe("summarizeChecks", () => {
  it("resumen todo ok", () => {
    const rs = ["a", "b", "c", "d", "e"].map(ok);
    expect(summarizeChecks(rs)).toEqual({ ok: 5, fail: 0, unknown: 0, verdict: "ok" });
  });

  it("un fail manda", () => {
    const rs = [ok("a"), ok("b"), ok("c"), ok("d"), fail("e")];
    expect(summarizeChecks(rs).verdict).toBe("fail");
  });

  it("unknown sin fail", () => {
    const rs = [ok("a"), ok("b"), ok("c"), ok("d"), unknown("e")];
    expect(summarizeChecks(rs).verdict).toBe("unknown");
  });

  it("lista vacia", () => {
    expect(summarizeChecks([])).toEqual({ ok: 0, fail: 0, unknown: 0, verdict: "ok" });
  });
});

describe("stepsToHighlight", () => {
  it("resalta el paso del check fallado", () => {
    expect(stepsToHighlight(GUIDE, [fail("chk-token")])).toEqual(["gl-02-token"]);
  });

  it("resalta varios sin repetir, en el orden de guide.checks", () => {
    expect(stepsToHighlight(GUIDE, [fail("chk-proyecto"), fail("chk-instancia")])).toEqual([
      "gl-01-instancia",
      "gl-04-project-path",
    ]);
  });

  it("no resalta si no hay guia", () => {
    expect(stepsToHighlight(null, [fail("chk-token")])).toEqual([]);
  });

  it("no resalta los ok", () => {
    expect(stepsToHighlight(GUIDE, [ok("chk-token"), unknown("chk-scope")])).toEqual([]);
  });
});

describe("canVerify", () => {
  it("canVerify exige url y path", () => {
    expect(canVerify({})).toBe(false);
    expect(canVerify({ gitlab_url: "https://gitlab.com" })).toBe(false);
    expect(canVerify({ gitlab_project: "acme/api" })).toBe(false);
    expect(canVerify({ gitlab_url: "https://gitlab.com", gitlab_project: "acme/api" })).toBe(true);
  });
});

describe("fallback embebido", () => {
  it("fallback tiene contenido", () => {
    expect(GITLAB_FALLBACK_GUIDE.steps.length).toBeGreaterThanOrEqual(3);
    for (const s of GITLAB_FALLBACK_GUIDE.steps) {
      expect(s.title.trim().length).toBeGreaterThan(0);
      expect(s.detail.trim().length).toBeGreaterThan(0);
    }
  });

  it("isServerGuide distingue", () => {
    expect(isServerGuide(GITLAB_FALLBACK_GUIDE)).toBe(false);
    expect(isServerGuide(GUIDE)).toBe(true);
    expect(isServerGuide(null)).toBe(false);
  });
});

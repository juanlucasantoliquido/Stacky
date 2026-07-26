// Plan 200 F4 — Badge de "despliegue SQL requerido".
import { describe, it, expect } from "vitest";
import { badge, scriptsSummary, type DeployNeed } from "./sqlDeployBadge";

function need(over: Partial<DeployNeed> = {}): DeployNeed {
  return {
    requires: true,
    confidence: "alta",
    scripts: [{ name: "cambio.sql", sha256: "abc", source: "incident_attachment" }],
    suggested_environments: ["QA", "PROD"],
    reason: "hay un .sql adjunto",
    ...over,
  };
}

describe("badge", () => {
  it("sin necesidad de despliegue no se muestra nada", () => {
    expect(badge(need({ requires: false }))).toEqual({ show: false, tone: "info", text: "" });
  });

  it("certeza alta: tono warn con el conteo", () => {
    expect(badge(need())).toEqual({
      show: true,
      tone: "warn",
      text: "Despliegue SQL requerido — 1 script(s)",
    });
  });

  it("sospecha: tono info, no warn", () => {
    // Si la sospecha se viera igual que la certeza, el operador dejaría de
    // mirar los warn.
    const b = badge(need({ confidence: "posible" }));

    expect(b.tone).toBe("info");
    expect(b.text).toBe("Posible despliegue SQL (revisar)");
  });

  it("el conteo refleja los scripts de verdad", () => {
    const b = badge(need({
      scripts: [
        { name: "a.sql", sha256: "1", source: "x" },
        { name: "b.sql", sha256: "2", source: "x" },
      ],
    }));

    expect(b.text).toContain("2 script(s)");
  });

  it("un objeto vacío no rompe la pantalla", () => {
    expect(badge({} as DeployNeed).show).toBe(false);
  });
});

describe("scriptsSummary", () => {
  it("lista los scripts y los ambientes sugeridos", () => {
    expect(scriptsSummary(need({
      scripts: [
        { name: "a.sql", sha256: "1", source: "x" },
        { name: "b.sql", sha256: "2", source: "x" },
      ],
    }))).toBe("a.sql, b.sql en QA, PROD");
  });

  it("sin ambientes sugeridos no deja un 'en' colgando", () => {
    expect(scriptsSummary(need({ suggested_environments: [] }))).toBe("cambio.sql");
  });

  it("vacío si no requiere despliegue", () => {
    expect(scriptsSummary(need({ requires: false }))).toBe("");
  });

  it("vacío si requiere pero no hay scripts nombrables", () => {
    // El caso "posible" por keywords: hay sospecha, no hay archivos.
    expect(scriptsSummary(need({ confidence: "posible", scripts: [] }))).toBe("");
  });
});

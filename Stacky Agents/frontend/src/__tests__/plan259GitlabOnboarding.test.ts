/**
 * Plan 259 F5 — Logica pura del alta GitLab.
 *
 * RTL/jsdom NO estan instalados en este repo (gotcha de la casa), asi que TODA
 * la logica testeable vive en `src/projects/newProjectGitlabModel.ts` y el `.tsx`
 * solo pinta.
 */
import { describe, it, expect } from "vitest";
import {
  GITLAB_FIELD_DOM_ORDER,
  engineCheckboxDefault,
  engineNoticeFor,
  humanizeApiError,
  normalizeGitlabProjectPath,
  normalizeGitlabUrl,
  showGitlabTrackerButton,
  showInfoButton,
  validateGitlabFields,
} from "../projects/newProjectGitlabModel";

describe("validateGitlabFields", () => {
  it("valida url vacia", () => {
    const errs = validateGitlabFields({});
    expect(Object.keys(errs).sort()).toEqual([
      "gitlab_project",
      "gitlab_token",
      "gitlab_url",
    ]);
  });

  it("valida url sin esquema", () => {
    const errs = validateGitlabFields({ gitlab_url: "gitlab.com" });
    expect(errs.gitlab_url).toMatch(/http:\/\/ o https:\/\//);
  });

  it("rechaza /api/v4 al final", () => {
    const errs = validateGitlabFields({ gitlab_url: "https://gitlab.com/api/v4" });
    expect(errs.gitlab_url).toMatch(/\/api\/v4/);
  });

  it("acepta config completa", () => {
    expect(
      validateGitlabFields({
        gitlab_url: "https://gitlab.com",
        gitlab_project: "acme/api",
        gitlab_token: "glpat-" + "XYZ",
      })
    ).toEqual({});
  });

  it("rechaza url completa como path", () => {
    const errs = validateGitlabFields({
      gitlab_url: "https://gitlab.com",
      gitlab_project: "https://gitlab.com/acme/api",
      gitlab_token: "t",
    });
    expect(errs.gitlab_project).toMatch(/solo el path/);
  });
});

describe("normalizacion", () => {
  it("normaliza barra final", () => {
    expect(normalizeGitlabUrl("https://gitlab.com/")).toBe("https://gitlab.com");
  });

  it("normaliza /api/v4", () => {
    expect(normalizeGitlabUrl("https://gl.io/api/v4")).toBe("https://gl.io");
  });

  it("normaliza path desde url completa", () => {
    expect(normalizeGitlabProjectPath("https://gitlab.com/acme/backend/api/-/issues")).toBe(
      "acme/backend/api"
    );
  });

  it("path limpio no se toca", () => {
    expect(normalizeGitlabProjectPath("acme/api")).toBe("acme/api");
  });

  it("path numerico no se toca", () => {
    expect(normalizeGitlabProjectPath("4711")).toBe("4711");
  });
});

describe("casilla del motor", () => {
  it("motor tildado por default", () => {
    expect(engineCheckboxDefault(undefined)).toBe(true);
    expect(engineCheckboxDefault(false)).toBe(false);
    expect(engineCheckboxDefault(true)).toBe(true);
  });
});

describe("orden DOM", () => {
  it("orden dom cubre los 3 obligatorios", () => {
    // Sin esto, el foco-al-primer-error apunta a un campo inexistente.
    expect([...GITLAB_FIELD_DOM_ORDER].sort()).toEqual(
      Object.keys(validateGitlabFields({})).sort()
    );
  });
});

describe("visibilidad por flags (fail-open)", () => {
  it("muestra el boton GitLab si la flag no esta explicitamente en false", () => {
    expect(showGitlabTrackerButton({})).toBe(true);
    expect(showGitlabTrackerButton({ onboardingGitlab: true })).toBe(true);
    expect(showGitlabTrackerButton({ onboardingGitlab: false })).toBe(false);
  });

  it("el boton INFO solo aparece para gitlab", () => {
    expect(showInfoButton("gitlab", {})).toBe(true);
    expect(showInfoButton("azure_devops", {})).toBe(false);
    expect(showInfoButton("gitlab", { setupGuide: false })).toBe(false);
  });
});

describe("engineNoticeFor", () => {
  it("aviso de motor: sin resultado no dice nada", () => {
    expect(engineNoticeFor(undefined).level).toBe("none");
  });

  it("aviso de motor: encendido", () => {
    const n = engineNoticeFor({ changed: true });
    expect(n.level).toBe("info");
    expect(n.text).toMatch(/activad/i);
  });

  it("aviso de motor: ya estaba", () => {
    expect(engineNoticeFor({ already_on: true }).level).toBe("info");
  });

  it("aviso de motor: destildada", () => {
    // El operador lo decidio: no hay nada que avisar.
    expect(engineNoticeFor({ skipped: true }).level).toBe("none");
  });

  it("aviso de motor: error", () => {
    const n = engineNoticeFor({ error: "boom" });
    expect(n.level).toBe("warn");
    expect(n.text).toContain("Paridad de proveedores");
  });
});

describe("humanizeApiError", () => {
  // api.post LANZA en cualquier non-2xx: el 400 de la flag apagada llega como
  // Error("400 BAD REQUEST: {json}") y sin esto el operador lee JSON crudo.
  it("extrae el mensaje del cuerpo JSON", () => {
    expect(humanizeApiError('400 BAD REQUEST: {"ok":false,"error":"X"}')).toBe("X");
  });

  it("devuelve el texto tal cual si no hay JSON", () => {
    expect(humanizeApiError("Error de conexión")).toBe("Error de conexión");
  });

  it("devuelve el texto crudo si el JSON no parsea", () => {
    expect(humanizeApiError("500 X: no-json{")).toBe("500 X: no-json{");
  });
});

import { describe, it, expect } from "vitest";
import {
  EMERGENCY_MODEL_CATALOG,
  resolveModelCatalog,
} from "../modelCatalogFallback";
import type { ModelCatalogResponse } from "../../api/endpoints";

describe("Plan 159 — fallback único de catálogo de modelos (función pura, sin DOM)", () => {
  it("EMERGENCY_MODEL_CATALOG contiene claude-sonnet-5", () => {
    const ids = EMERGENCY_MODEL_CATALOG.claude_code_cli.models.map((m) => m.id);
    expect(ids).toContain("claude-sonnet-5");
  });

  it("respuesta ok:false devuelve el fallback de emergencia", () => {
    const res: ModelCatalogResponse = { ok: false, runtimes: {} };
    expect(resolveModelCatalog(res)).toBe(EMERGENCY_MODEL_CATALOG);
  });

  it("null y undefined devuelven el fallback de emergencia", () => {
    expect(resolveModelCatalog(null)).toBe(EMERGENCY_MODEL_CATALOG);
    expect(resolveModelCatalog(undefined)).toBe(EMERGENCY_MODEL_CATALOG);
  });

  it("C7 — claude vacío se reemplaza SOLO claude_code_cli; copilot vivo se preserva", () => {
    const res: ModelCatalogResponse = {
      ok: true,
      runtimes: {
        claude_code_cli: {
          source: "static_config_file",
          default_model: "claude-sonnet-5",
          default_effort: "medium",
          models: [],
          efforts: [],
          effort_support: {},
        },
        github_copilot: {
          source: "live_introspection",
          default_model: null,
          default_effort: null,
          models: [{ id: "gpt-x", label: "X" }],
          efforts: [],
          effort_support: {},
        },
      },
    };
    const out = resolveModelCatalog(res);
    // claude_code_cli cayó a emergencia
    expect(out.claude_code_cli).toBe(EMERGENCY_MODEL_CATALOG.claude_code_cli);
    // github_copilot preserva su introspección viva
    expect(out.github_copilot.models.map((m) => m.id)).toContain("gpt-x");
  });

  it("claude con modelos reales devuelve los datos reales, no el fallback", () => {
    const res: ModelCatalogResponse = {
      ok: true,
      runtimes: {
        claude_code_cli: {
          source: "static_config_file",
          default_model: "x",
          default_effort: "medium",
          models: [{ id: "x", label: "X" }],
          efforts: [],
          effort_support: {},
        },
      },
    };
    const out = resolveModelCatalog(res);
    expect(out.claude_code_cli.models.map((m) => m.id)).toEqual(["x"]);
    expect(out).not.toBe(EMERGENCY_MODEL_CATALOG);
  });
});

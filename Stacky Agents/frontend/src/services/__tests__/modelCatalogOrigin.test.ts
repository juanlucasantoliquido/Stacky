import { describe, it, expect } from "vitest";
import { describirOrigenCatalogo } from "../modelCatalogOrigin";
import type { ModelCatalogResponse } from "../../api/endpoints";

/** Plan 288 F9 — los 10 casos de la tabla de reglas. */

const CLAUDE = "claude_code_cli";

const respuesta = (bloque: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
  ({
    ok: true,
    fallback_used: false,
    runtimes: { claude_code_cli: bloque },
    ...extra,
  }) as unknown as ModelCatalogResponse;

const CUENTA_OK = {
  disponible: true,
  motivo: "ok",
  suscripcion: "claude_max",
  nivel_de_limite: "default_claude_max_20x",
  agregados: [],
  omitidos: [],
};

describe("Plan 288 F9 — de dónde salió la lista", () => {
  it("origen_sin_respuesta", () => {
    const a = describirOrigenCatalogo(null, CLAUDE);
    expect(a.nivel).toBe("respaldo");
    expect(a.texto).toContain("Lista de respaldo");
    expect(describirOrigenCatalogo(undefined, CLAUDE).nivel).toBe("respaldo");
  });

  it("origen_no_ok", () => {
    const a = describirOrigenCatalogo(
      { ok: false, reason: "catalog_disabled", runtimes: {} } as ModelCatalogResponse,
      CLAUDE,
    );
    expect(a.nivel).toBe("respaldo");
    expect(a.detalle).toBe("catalog_disabled");
  });

  it("origen_respaldo_nombra_el_motivo", () => {
    const a = describirOrigenCatalogo(
      respuesta({ models: [] }, { fallback_used: true, error: "archivo ilegible" }),
      CLAUDE,
    );
    expect(a.nivel).toBe("respaldo");
    // El motivo se NOMBRA, no se esconde.
    expect(a.texto).toContain("archivo ilegible");
    expect(a.detalle).toBe("archivo ilegible");
  });

  it("origen_todo_bien_no_molesta", () => {
    const a = describirOrigenCatalogo(
      respuesta({ models: [{ id: "claude-sonnet-5" }], cuenta: CUENTA_OK }),
      CLAUDE,
    );
    expect(a.nivel).toBe("ok");
    expect(a.texto).toBe("");
  });

  it("origen_cuenta_ilegible_es_parcial", () => {
    const a = describirOrigenCatalogo(
      respuesta({
        models: [{ id: "claude-sonnet-5" }],
        cuenta: { ...CUENTA_OK, disponible: false, motivo: "sin_archivos" },
      }),
      CLAUDE,
    );
    expect(a.nivel).toBe("parcial");
    expect(a.texto).toContain("no se encontraron los archivos");
  });

  it("origen_cuenta_ausente_no_es_problema", () => {
    // El caso REAL de codex_cli y github_copilot: F11 prohíbe agregarles la clave.
    const res = {
      ok: true,
      fallback_used: false,
      runtimes: { codex_cli: { models: [{ id: "" }] } },
    } as unknown as ModelCatalogResponse;
    expect(describirOrigenCatalogo(res, "codex_cli").nivel).toBe("ok");
    expect(describirOrigenCatalogo(res, "codex_cli").texto).toBe("");
    // Y el bloque de Claude sin `cuenta` tampoco es un problema.
    const sinCuenta = describirOrigenCatalogo(respuesta({ models: [] }), CLAUDE);
    expect(sinCuenta.nivel).toBe("ok");
  });

  it("origen_copilot_con_error", () => {
    const res = {
      ok: true,
      fallback_used: false,
      runtimes: { github_copilot: { models: [], error: "401 sin sesión" } },
    } as unknown as ModelCatalogResponse;
    const a = describirOrigenCatalogo(res, "github_copilot");
    expect(a.nivel).toBe("parcial");
    expect(a.texto).toContain("401 sin sesión");
  });

  it("origen_omitidos_se_explican", () => {
    const a = describirOrigenCatalogo(
      respuesta({
        models: [{ id: "claude-sonnet-5" }],
        cuenta: {
          ...CUENTA_OK,
          omitidos: [
            { id: "glm-4.7", motivo: "otro_proveedor" },
            { id: "claude-fable-5", motivo: "bloqueado_por_politica_de_costo" },
          ],
        },
      }),
      CLAUDE,
    );
    expect(a.nivel).toBe("parcial");
    expect(a.texto).toContain("2");
    // Los motivos, en castellano.
    expect(a.detalle).toContain("no es un modelo de Claude Code");
    expect(a.detalle).toContain("bloqueado por política de costo");
    expect(a.detalle).toContain("glm-4.7");
  });

  it("origen_avisa_lo_del_agente_de_despliegue", () => {
    const a = describirOrigenCatalogo(
      respuesta({
        models: [{ id: "claude-sonnet-5" }, { id: "claude-opus-5" }],
        cuenta: {
          ...CUENTA_OK,
          omitidos: [{ id: "glm-4.7", motivo: "otro_proveedor" }],
        },
      }),
      CLAUDE,
    );
    expect(a.detalle).toContain("mantenimiento y despliegue");
    // Contra-prueba: sin ids de tier alto NO se dice.
    const sinOpus = describirOrigenCatalogo(
      respuesta({
        models: [{ id: "claude-sonnet-5" }],
        cuenta: {
          ...CUENTA_OK,
          omitidos: [{ id: "glm-4.7", motivo: "otro_proveedor" }],
        },
      }),
      CLAUDE,
    );
    expect(sinOpus.detalle).not.toContain("mantenimiento y despliegue");
  });

  it("origen_motor_desconocido_no_lanza", () => {
    const a = describirOrigenCatalogo(respuesta({ models: [] }), "motor_inventado");
    expect(a.nivel).toBe("respaldo");
    expect(() => describirOrigenCatalogo(respuesta({ models: [] }), "")).not.toThrow();
  });
});

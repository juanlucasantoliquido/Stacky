import { describe, it, expect } from "vitest";
import { GatewayError, userFacingMessage } from "../gatewayError";

/**
 * Plan 273 F4 (B-02) — el error conserva el mensaje humano y el correlation_id
 * SIN romper a los 7 sitios que parsean el string aplanado.
 *
 * Test PURO (sin DOM): solo la clase y la funcion.
 */

const body = (o: Record<string, unknown>) => JSON.stringify(o);

describe("plan273 F4 — GatewayError conserva el contrato del message", () => {
  it("message_es_byte_identico_al_formato_historico", () => {
    // EL CASO MAS IMPORTANTE DEL ARCHIVO. 7 sitios de produccion parsean este
    // formato exacto; romperlo los hace tomar la rama equivocada EN SILENCIO.
    const e = new GatewayError(403, "FORBIDDEN", '{"ok":false}');
    expect(e.message).toBe('403 FORBIDDEN: {"ok":false}');
  });

  it("los_7_parsers_legacy_siguen_funcionando", () => {
    const e = new GatewayError(403, "FORBIDDEN", '{"ok":false}');
    expect(e.message.startsWith("403")).toBe(true);          // CompareWizard
    expect(e.message.indexOf(": ")).toBeGreaterThanOrEqual(0); // ProductionFlow, SectionDoctor, Variables
    expect(e.message.match(/^(\d{3})\s/)?.[1]).toBe("403");   // ExecutionErrorAnalysisBlock
    expect(String(e).includes("403")).toBe(true);             // AgentLaunchModal
  });

  it("preserva_status_y_errorBody", () => {
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      body({ error: "feature_disabled", message: "X", correlation_id: "a3f9c1" })
    );
    expect(e.status).toBe(403);
    expect(e.errorBody?.message).toBe("X");
    expect(e.correlationId).toBe("a3f9c1");
  });

  it("body_no_json_no_explota", () => {
    const e = new GatewayError(502, "BAD GATEWAY", "<html>502</html>");
    expect(e.errorBody).toBeNull();
  });

  it("body_vacio_no_explota", () => {
    const e = new GatewayError(500, "INTERNAL SERVER ERROR", "");
    expect(e.errorBody).toBeNull();
  });
});

describe("plan273 F4 — userFacingMessage", () => {
  it("ufm_prioriza_el_message_del_backend", () => {
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      body({ error: "feature_disabled", message: "El Comparador de BD está desactivado." })
    );
    expect(userFacingMessage(e).title).toBe("El Comparador de BD está desactivado.");
  });

  it("ufm_nunca_devuelve_status_crudo", () => {
    const e = new GatewayError(500, "INTERNAL SERVER ERROR", "");
    expect(userFacingMessage(e).title).not.toMatch(/^\d{3} [A-Z ]+:/);
  });

  it("ufm_nunca_devuelve_json_crudo", () => {
    const e = new GatewayError(500, "INTERNAL SERVER ERROR", body({ ok: false, trace: "..." }));
    const title = userFacingMessage(e).title;
    expect(title).not.toMatch(/^\s*[{[]/);
    // ENDURECIDO durante la implementacion: con `^\s*[{[]` SOLO, este caso pasaba
    // con la version ingenua, porque el string aplanado empieza con "500 ", no con
    // "{" — o sea no discriminaba y no medía nada. El JSON crudo no tiene que
    // aparecer en NINGUNA posicion del texto que ve el operador.
    expect(title).not.toContain('{"');
    expect(title).not.toContain("trace");
  });

  it("ufm_nunca_filtra_STACKY", () => {
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      body({ error: "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)." })
    );
    const r = userFacingMessage(e);
    expect(r.title).not.toMatch(/STACKY_[A-Z_]+/);
    expect(r.flag).toBe("STACKY_DB_COMPARE_ENABLED");
  });

  it("ufm_extrae_la_flag_de_detail", () => {
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      body({ error: "feature_disabled", message: "Apagado.", detail: { flag: "STACKY_DOCS_GRAPH_ENABLED" } })
    );
    expect(userFacingMessage(e).flag).toBe("STACKY_DOCS_GRAPH_ENABLED");
  });

  it("ufm_403_de_flag_usa_message_no_error", () => {
    const e = new GatewayError(
      403,
      "FORBIDDEN",
      body({ error: "feature_disabled", message: "El grafo está desactivado." })
    );
    expect(userFacingMessage(e).title).toBe("El grafo está desactivado.");
  });

  it("ufm_error_de_red", () => {
    const r = userFacingMessage(new Error("Failed to fetch"));
    expect(r.title).toBe("No se pudo conectar con el servidor.");
    expect(r.isTimeout).toBe(false);
  });

  it("ufm_un_typeerror_de_render_no_se_disfraza_de_error_de_red", () => {
    // v2 C14 — GATE CONTRA LA REGRESION. PageErrorBoundary recibe crashes de
    // RENDER, no errores de API (el crash vivo del 266 en radarLogic.ts:60 es un
    // TypeError). Con el algoritmo sin el paso 0 esto se mostraba como
    // "No se pudo conectar con el servidor.", o sea F4 EMPEORABA el unico archivo
    // de UI que toca: hoy ese boundary muestra el TypeError real.
    const msg = "Cannot read properties of undefined (reading 'summary')";
    const r = userFacingMessage(new TypeError(msg));
    expect(r.title).toBe(msg);
    expect(r.title).not.toBe("No se pudo conectar con el servidor.");
  });

  it("ufm_conserva_el_saneamiento_en_el_paso_0", () => {
    // El paso 0 devuelve el message del programa, PERO SANEADO: no es un bypass.
    const r = userFacingMessage(new Error("Fallo raro con STACKY_DB_COMPARE_ENABLED adentro"));
    expect(r.title).not.toMatch(/STACKY_[A-Z_]+/);
  });

  it("ufm_valor_no_error", () => {
    for (const v of ["algo", null, undefined, 42]) {
      const r = userFacingMessage(v);
      expect(r.title.length).toBeGreaterThan(0);
    }
  });

  it("ufm_correlation_id_no_va_en_el_title", () => {
    const e = new GatewayError(
      500,
      "INTERNAL SERVER ERROR",
      body({ message: "Algo salió mal.", correlation_id: "deadbeef" })
    );
    const r = userFacingMessage(e);
    expect(r.title).not.toContain("deadbeef");
    expect(r.correlationId).toBe("deadbeef");
  });

  it("ufm_familias_de_status_sin_message", () => {
    const t = (s: number, st: string) => userFacingMessage(new GatewayError(s, st, "")).title;
    expect(t(403, "FORBIDDEN")).toBe("Esta funcionalidad está desactivada.");
    expect(t(404, "NOT FOUND")).toBe("Esta funcionalidad está desactivada.");
    expect(t(409, "CONFLICT")).toBe("Ya hay una operación en curso.");
    expect(t(500, "INTERNAL SERVER ERROR")).toBe(
      "El servidor tuvo un problema al procesar la solicitud."
    );
    expect(t(418, "IM A TEAPOT")).toBe("No se pudo completar la operación.");
  });
});

// Plan 165 F1 — Tests del contrato de rutas (lógica pura, sin jsdom).
// parseRoute/serializeRoute reciben pathname+search y no tocan window.
import { describe, it, expect } from "vitest";
import { parseRoute, serializeRoute, tabFromSegments } from "../routes";

/** Parte una URL "path?search" en el par [pathname, search] que parseRoute espera. */
function split(url: string): [string, string] {
  const i = url.indexOf("?");
  return i === -1 ? [url, ""] : [url.slice(0, i), url.slice(i)];
}

describe("parseRoute (Plan 165 F1)", () => {
  it("parse_primer_nivel", () => {
    expect(parseRoute("/history", "")).toEqual({
      tab: "history", subtab: undefined, exec: undefined, query: {},
    });
    expect(parseRoute("/", "").tab).toBe("team");
  });

  it("parse_subtab", () => {
    const r = parseRoute("/settings/appearance", "");
    expect(r.tab).toBe("settings");
    expect(r.subtab).toBe("appearance");
  });

  it("parse_exec_canonico", () => {
    expect(parseRoute("/history", "?exec=123").exec).toBe(123);
  });

  it("parse_exec_alias", () => {
    expect(parseRoute("/history", "?execution=123").exec).toBe(123);
  });

  it("parse_exec_raiz_normaliza", () => {
    const r = parseRoute("/", "?exec=123");
    expect(r.tab).toBe("history");
    expect(r.exec).toBe(123);
  });

  it("parse_query_desconocida_preserva", () => {
    const r = parseRoute("/docs", "?path=a/b&flag=X");
    expect(r.query).toEqual({ path: "a/b", flag: "X" });
  });

  it("parse_doble_slash", () => {
    expect(parseRoute("//history", "").tab).toBe("history");
    expect(parseRoute("/settings//appearance", "").subtab).toBe("appearance");
  });

  it("parse_trailing_slash", () => {
    const r = parseRoute("/history/", "");
    expect(r.tab).toBe("history");
    expect(r.subtab).toBeUndefined();
  });

  it("parse_exec_no_numerico", () => {
    expect(parseRoute("/history", "?exec=abc").exec).toBeUndefined();
  });

  it("parse_exec_vacio_y_formas_raras", () => {
    expect(parseRoute("/history", "?exec=").exec).toBeUndefined();
    expect(parseRoute("/history", "?exec=0x10").exec).toBeUndefined();
    expect(parseRoute("/history", "?exec=1.5").exec).toBeUndefined();
    expect(parseRoute("/history", "?exec=-3").exec).toBeUndefined();
  });

  it("parse_ambas_claves", () => {
    const r = parseRoute("/history", "?exec=1&execution=2");
    expect(r.exec).toBe(1);
    expect(r.query).not.toHaveProperty("execution");
    expect(r.query).not.toHaveProperty("exec");
  });

  it("parse_tab_desconocido_sin_subtab", () => {
    const r = parseRoute("/nonexistent/foo", "");
    expect(r.tab).toBe("team");
    expect(r.subtab).toBeUndefined();
    expect(serializeRoute(r)).toBe("/");
    // idempotencia §4: re-parsear la forma canónica devuelve el mismo estado
    expect(parseRoute(...split(serializeRoute(r)))).toEqual(r);
  });
});

describe("serializeRoute (Plan 165 F1)", () => {
  it("serialize_canonico", () => {
    expect(serializeRoute({ tab: "settings", subtab: "appearance", query: {} }))
      .toBe("/settings/appearance");
    expect(serializeRoute({ tab: "history", exec: 123, query: {} }))
      .toBe("/history?exec=123");
  });

  it("serialize_preserva_query", () => {
    const out = serializeRoute({ tab: "docs", query: { path: "a/b" } });
    const r = parseRoute(...split(out));
    expect(r.query.path).toBe("a/b");
  });
});

describe("round-trip (Plan 165 F1)", () => {
  it("roundtrip_identidad_canonica", () => {
    for (const url of ["/history", "/settings/appearance", "/history?exec=9", "/tickets"]) {
      expect(serializeRoute(parseRoute(...split(url)))).toBe(url);
    }
  });

  it("roundtrip_idempotente_no_canonica", () => {
    for (const url of ["/?exec=123", "/history?execution=123"]) {
      const once = parseRoute(...split(url));
      const twice = parseRoute(...split(serializeRoute(once)));
      expect(twice).toEqual(once);
    }
  });

  it("tabFromSegments_raiz_y_desconocido_team", () => {
    expect(tabFromSegments([])).toBe("team");
    expect(tabFromSegments(["nope"])).toBe("team");
    expect(tabFromSegments(["history"])).toBe("history");
  });
});

// Plan 165 F2 — Tests de serialización de filtros a/desde querystring (puros).
import { describe, it, expect } from "vitest";
import {
  historyFiltersToQuery, historyFiltersFromQuery,
  sysLogFiltersToQuery, sysLogFiltersFromQuery,
  HISTORY_FILTER_QUERY_KEYS, omitKeys, resolveMountFilters,
  type HistoryFilters, type SysLogFilters,
} from "../routeFilters";

const HISTORY_DEF: HistoryFilters = {
  agent_type: "", runtime: "", status: "", days: "", limit: 50, offset: 0,
};

const SYSLOG_FULL: SysLogFilters = {
  level: "ERROR", source: "agent_runner", action: "started", q: "boom",
  execution_id: "10", ticket_id: "20", from: "2026-01-01", to: "2026-02-01",
};

describe("historyFilters (Plan 165 F2)", () => {
  it("history_to_query_omite_vacios_y_offset", () => {
    const out = historyFiltersToQuery({
      agent_type: "qa", runtime: "", status: "error", days: "",
      limit: 50, offset: 100,
    });
    expect(out).toEqual({ agent_type: "qa", status: "error" });
    expect(out).not.toHaveProperty("offset");
    expect(out).not.toHaveProperty("limit");
    expect(out).not.toHaveProperty("runtime");
  });

  it("history_roundtrip", () => {
    const f: HistoryFilters = {
      agent_type: "qa", runtime: "codex_cli", status: "error", days: "7",
      limit: 50, offset: 200,
    };
    expect(historyFiltersFromQuery(historyFiltersToQuery(f))).toEqual({
      agent_type: "qa", runtime: "codex_cli", status: "error", days: "7",
    });
  });

  it("offset_nunca_en_query", () => {
    const out = historyFiltersToQuery({ ...HISTORY_DEF, offset: 999 });
    expect(Object.keys(out)).not.toContain("offset");
  });
});

describe("sysLogFilters (Plan 165 F2)", () => {
  it("syslog_to_query_8_campos", () => {
    expect(Object.keys(sysLogFiltersToQuery(SYSLOG_FULL))).toHaveLength(8);
    const partial: SysLogFilters = {
      ...SYSLOG_FULL, source: "", action: "", from: "", to: "",
    };
    expect(sysLogFiltersToQuery(partial)).toEqual({
      level: "ERROR", q: "boom", execution_id: "10", ticket_id: "20",
    });
  });

  it("syslog_roundtrip", () => {
    expect(sysLogFiltersFromQuery(sysLogFiltersToQuery(SYSLOG_FULL))).toEqual(SYSLOG_FULL);
  });
});

describe("resolveMountFilters (Plan 165 F2 · C2/C5)", () => {
  it("resolve_mount_url_gana_completa", () => {
    const out = resolveMountFilters(
      HISTORY_DEF,
      { status: "error", agent_type: "qa" },
      { status: "running" },
    );
    // con >=1 clave en la URL, lo persistido se IGNORA entero
    expect(out).toEqual({ ...HISTORY_DEF, status: "running" });
    expect(out.agent_type).toBe("");
  });

  it("resolve_mount_sin_url_usa_persistido", () => {
    const out = resolveMountFilters(HISTORY_DEF, { status: "error" }, {});
    expect(out).toEqual({ ...HISTORY_DEF, status: "error" });
  });

  it("resolve_mount_anti_drift", () => {
    // shape persistido viejo (le falta 'days'): se completa con el default, sin undefined
    const shapeViejo = {
      agent_type: "qa", runtime: "", status: "", limit: 50, offset: 0,
    } as Partial<HistoryFilters>;
    const out = resolveMountFilters(HISTORY_DEF, shapeViejo, {});
    expect(out.days).toBe("");
    expect(Object.values(out).every((v) => v !== undefined)).toBe(true);
  });
});

describe("omitKeys (Plan 165 F2)", () => {
  it("omit_keys", () => {
    expect(omitKeys({ a: "1", agent_type: "qa" }, HISTORY_FILTER_QUERY_KEYS))
      .toEqual({ a: "1" });
  });
});

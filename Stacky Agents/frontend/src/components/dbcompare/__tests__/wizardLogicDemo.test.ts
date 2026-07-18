import { describe, it, expect } from "vitest";
import { selectableTargets, canLaunch } from "../wizardLogic";
import type { DbEnvironment } from "../dbcompareTypes";

// Plan 183 §3.2 / KPI-7 — regla nueva: sqlite (carril test-*) es seleccionable SIN
// contraseña; sqlserver/oracle conservan el gate EXACTO (ambas direcciones).

function env(partial: Partial<DbEnvironment>): DbEnvironment {
  return {
    alias: "env-a",
    engine: "sqlite",
    host: "",
    port: 0,
    database: "/tmp/demo.db",
    username: "demo",
    odbc_driver: "",
    schema_filter: null,
    notes: "",
    created_at: "",
    last_used_at: null,
    has_password: false,
    latest_snapshot_taken_at: null,
    latest_snapshot_hash8: null,
    ...partial,
  };
}

describe("Plan 183 — wizardLogic sqlite sin contraseña", () => {
  it("sqlite sin password ⇒ target habilitado", () => {
    const source = env({ alias: "test-demo-dev", engine: "sqlite", has_password: false });
    const target = env({ alias: "test-demo-test", engine: "sqlite", has_password: false });
    const out = selectableTargets([target], source);
    expect(out[0]).toEqual({ alias: "test-demo-test", enabled: true, reason: "" });
  });

  it("sqlite sin password ⇒ canLaunch ok", () => {
    const source = env({ alias: "test-demo-dev", engine: "sqlite", has_password: false });
    const target = env({ alias: "test-demo-test", engine: "sqlite", has_password: false });
    expect(canLaunch(source, target)).toEqual({ ok: true, reason: "" });
  });

  it("sqlserver sin password ⇒ target sigue deshabilitado (regla intacta)", () => {
    const source = env({ alias: "src", engine: "sqlserver", has_password: true });
    const target = env({ alias: "tgt", engine: "sqlserver", has_password: false });
    const out = selectableTargets([target], source);
    expect(out[0].enabled).toBe(false);
    expect(out[0].reason).toMatch(/contraseña/i);
  });

  it("sqlserver sin password ⇒ canLaunch NO ok (regla intacta)", () => {
    const source = env({ alias: "src", engine: "sqlserver", has_password: false });
    const target = env({ alias: "tgt", engine: "sqlserver", has_password: true });
    const out = canLaunch(source, target);
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/contraseña/i);
  });
});

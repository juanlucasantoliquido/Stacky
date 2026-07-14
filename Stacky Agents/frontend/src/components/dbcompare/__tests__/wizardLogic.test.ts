import { describe, it, expect } from "vitest";
import { selectableTargets, canLaunch } from "../wizardLogic";
import type { DbEnvironment } from "../dbcompareTypes";

function env(partial: Partial<DbEnvironment>): DbEnvironment {
  return {
    alias: "env-a",
    engine: "sqlserver",
    host: "host",
    port: 1433,
    database: "db",
    username: "user",
    has_password: true,
    latest_snapshot_taken_at: null,
    latest_snapshot_hash8: null,
    ...partial,
  };
}

describe("Plan 124 F2 — wizardLogic (pure)", () => {
  describe("selectableTargets", () => {
    it("sin origen elegido -> todos deshabilitados", () => {
      const envs = [env({ alias: "a" }), env({ alias: "b" })];
      const out = selectableTargets(envs, null);
      expect(out.every((t) => t.enabled === false)).toBe(true);
    });

    it("mismo engine y con password -> habilitado", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const envs = [env({ alias: "tgt", engine: "sqlserver", has_password: true })];
      const out = selectableTargets(envs, source);
      expect(out).toEqual([{ alias: "tgt", enabled: true, reason: "" }]);
    });

    it("distinto engine -> deshabilitado con motivo de motor", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const envs = [env({ alias: "tgt", engine: "oracle" })];
      const out = selectableTargets(envs, source);
      expect(out[0].enabled).toBe(false);
      expect(out[0].reason).toMatch(/motor/i);
    });

    it("mismo alias que el origen -> deshabilitado", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const envs = [env({ alias: "src", engine: "sqlserver" })];
      const out = selectableTargets(envs, source);
      expect(out[0].enabled).toBe(false);
      expect(out[0].reason).toMatch(/mismo ambiente/i);
    });

    it("sin password -> deshabilitado", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const envs = [env({ alias: "tgt", engine: "sqlserver", has_password: false })];
      const out = selectableTargets(envs, source);
      expect(out[0].enabled).toBe(false);
      expect(out[0].reason).toMatch(/contraseña/i);
    });
  });

  describe("canLaunch", () => {
    it("selección válida -> ok", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const target = env({ alias: "tgt", engine: "sqlserver" });
      expect(canLaunch(source, target)).toEqual({ ok: true, reason: "" });
    });

    it("motor distinto -> no ok", () => {
      const source = env({ alias: "src", engine: "sqlserver" });
      const target = env({ alias: "tgt", engine: "oracle" });
      const out = canLaunch(source, target);
      expect(out.ok).toBe(false);
      expect(out.reason).toMatch(/motor/i);
    });

    it("sin origen -> no ok", () => {
      const out = canLaunch(null, env({ alias: "tgt" }));
      expect(out.ok).toBe(false);
    });

    it("sin destino -> no ok", () => {
      const out = canLaunch(env({ alias: "src" }), null);
      expect(out.ok).toBe(false);
    });
  });
});

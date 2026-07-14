import { describe, expect, it } from "vitest";
import { validateEnvironmentForm, defaultPortFor } from "../envForm";

describe("validateEnvironmentForm", () => {
  const base = {
    alias: "PACIFICO-DEV",
    engine: "sqlserver",
    host: "host1",
    port: 1433,
    database: "RSPACIFICO",
    username: "ro_user",
  };

  it("form válido no tiene errores", () => {
    const r = validateEnvironmentForm(base);
    expect(r.ok).toBe(true);
    expect(r.errors).toEqual({});
  });

  it("alias inválido produce error", () => {
    const r = validateEnvironmentForm({ ...base, alias: "bad alias!" });
    expect(r.ok).toBe(false);
    expect(r.errors.alias).toBeTruthy();
  });

  it("engine fuera de lista produce error", () => {
    const r = validateEnvironmentForm({ ...base, engine: "mysql" });
    expect(r.ok).toBe(false);
    expect(r.errors.engine).toBeTruthy();
  });

  it("port fuera de rango produce error", () => {
    const r = validateEnvironmentForm({ ...base, port: 70000 });
    expect(r.ok).toBe(false);
    expect(r.errors.port).toBeTruthy();
  });

  it("campos vacíos (host/database/username) producen error cada uno", () => {
    const r = validateEnvironmentForm({ ...base, host: "", database: "  ", username: "" });
    expect(r.ok).toBe(false);
    expect(r.errors.host).toBeTruthy();
    expect(r.errors.database).toBeTruthy();
    expect(r.errors.username).toBeTruthy();
  });
});

describe("defaultPortFor", () => {
  it("sqlserver → 1433", () => {
    expect(defaultPortFor("sqlserver")).toBe(1433);
  });

  it("oracle → 1521", () => {
    expect(defaultPortFor("oracle")).toBe(1521);
  });
});

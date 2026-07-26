// Plan 200 R3/R4 — Lógica pura del panel de ejecución SQL.
import { describe, it, expect } from "vitest";
import {
  deployStatus,
  deployStatusByEnv,
  executableEnvs,
  idempotencyWarning,
  ledgerRow,
  sha256Hex,
  type EnvOption,
  type LedgerEntry,
} from "./sqlExecPanelLogic";

function env(over: Partial<EnvOption> = {}): EnvOption {
  return { alias: "QA", engine: "sqlserver", exec_allowed: true, has_password: true, ...over };
}

function entry(over: Partial<LedgerEntry> = {}): LedgerEntry {
  return {
    alias: "QA",
    ticket_ref: "T-1",
    script_sha256: "abc",
    result_ok: true,
    rows_affected: 3,
    dry_run: false,
    executed_at: "2026-07-26T10:00:00+00:00",
    executed_by: "operador",
    error: null,
    ...over,
  };
}

describe("executableEnvs", () => {
  it("deja fuera los que no tienen el opt-in de escritura", () => {
    const out = executableEnvs([env({ alias: "QA" }), env({ alias: "PROD", exec_allowed: false })]);

    expect(out.map((e) => e.alias)).toEqual(["QA"]);
  });

  it("deja fuera los que no tienen credencial", () => {
    // Ofrecerlo sería ofrecer un botón que siempre falla.
    const out = executableEnvs([env({ alias: "QA", has_password: false })]);

    expect(out).toEqual([]);
  });

  it("el orden no depende de cómo vinieron", () => {
    const a = executableEnvs([env({ alias: "B" }), env({ alias: "A" })]);

    expect(a.map((e) => e.alias)).toEqual(["A", "B"]);
  });

  it("lista vacía o nula no rompe", () => {
    expect(executableEnvs([])).toEqual([]);
    expect(executableEnvs(null as unknown as EnvOption[])).toEqual([]);
  });
});

describe("idempotencyWarning", () => {
  it("avisa con la fecha si ya se aplicó", () => {
    expect(idempotencyWarning([entry()], "QA", "abc")).toBe("Ya ejecutado el 2026-07-26 10:00:00");
  });

  it("otro ambiente o otro script no cuentan", () => {
    expect(idempotencyWarning([entry()], "PROD", "abc")).toBe("");
    expect(idempotencyWarning([entry()], "QA", "otro")).toBe("");
  });

  it("un dry-run no es una ejecución", () => {
    expect(idempotencyWarning([entry({ dry_run: true })], "QA", "abc")).toBe("");
  });

  it("un intento fallido tampoco: no quedó aplicado", () => {
    expect(idempotencyWarning([entry({ result_ok: false })], "QA", "abc")).toBe("");
  });
});

describe("ledgerRow", () => {
  it("formato de una ejecución OK", () => {
    expect(ledgerRow(entry())).toBe("2026-07-26 10:00:00 · QA · OK · 3 filas");
  });

  it("formato de un fallo", () => {
    expect(ledgerRow(entry({ result_ok: false, rows_affected: null }))).toBe(
      "2026-07-26 10:00:00 · QA · FALLO",
    );
  });

  it("un dry-run se distingue de una ejecución real", () => {
    // Confundirlos haría creer que algo se aplicó cuando solo se previsualizó.
    expect(ledgerRow(entry({ dry_run: true }))).toContain("DRY-RUN");
  });
});

describe("deployStatus", () => {
  it("sin registro es 'no-registrado', no 'no aplicado'", () => {
    // No es lo mismo "sé que no está" que "no sé".
    expect(deployStatus([], "QA", "abc").state).toBe("no-registrado");
  });

  it("una ejecución ok es 'aplicado'", () => {
    expect(deployStatus([entry()], "QA", "abc")).toEqual({
      state: "aplicado",
      detail: "aplicado (2026-07-26 10:00:00)",
    });
  });

  it("manda el intento MÁS RECIENTE, no el mejor", () => {
    // Si el último falló, decir "aplicado" por un ok viejo sería mentir sobre
    // el estado actual del ambiente.
    const out = deployStatus(
      [
        entry({ result_ok: true, executed_at: "2026-07-26T10:00:00+00:00" }),
        entry({ result_ok: false, executed_at: "2026-07-26T12:00:00+00:00" }),
      ],
      "QA",
      "abc",
    );

    expect(out.state).toBe("fallo");
  });

  it("y al revés: un fallo viejo no ensucia un ok nuevo", () => {
    const out = deployStatus(
      [
        entry({ result_ok: false, executed_at: "2026-07-26T08:00:00+00:00" }),
        entry({ result_ok: true, executed_at: "2026-07-26T09:00:00+00:00" }),
      ],
      "QA",
      "abc",
    );

    expect(out.state).toBe("aplicado");
  });

  it("los dry-run no cambian el estado", () => {
    const out = deployStatus(
      [
        entry({ result_ok: true, executed_at: "2026-07-26T10:00:00+00:00" }),
        entry({ dry_run: true, result_ok: true, executed_at: "2026-07-26T23:00:00+00:00" }),
      ],
      "QA",
      "abc",
    );

    expect(out.state).toBe("aplicado");
  });
});

describe("deployStatusByEnv", () => {
  it("un estado por ambiente, incluidos los que no tienen registro", () => {
    const mapa = deployStatusByEnv([entry({ alias: "QA" })], ["QA", "PROD"], "abc");

    expect(mapa).toEqual({ QA: "aplicado", PROD: "no-registrado" });
  });

  it("sin ambientes devuelve un mapa vacío", () => {
    expect(deployStatusByEnv([entry()], [], "abc")).toEqual({});
  });
});

describe("sha256Hex", () => {
  it("vector de prueba fijo, calculado aparte", async () => {
    // Valor obtenido con hashlib en Python, NO con esta misma función: si el
    // esperado saliera de acá mismo, el test pasaría aunque el hash estuviera
    // mal, y el fingerprint del HITL dejaría de ser comparable con el que
    // calcula el backend justo cuando importa.
    await expect(sha256Hex("SELECT 1")).resolves.toBe(
      "e004ebd5b5532a4b85984a62f8ad48a81aa3460c1ca07701f386135d72cdecf5",
    );
  });

  it("el vector del texto vacío también es el canónico", async () => {
    await expect(sha256Hex("")).resolves.toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("el mismo texto siempre da el mismo hash y textos distintos no colisionan", async () => {
    const a = await sha256Hex("SELECT 1");
    const b = await sha256Hex("SELECT 1");
    const c = await sha256Hex("SELECT 2");

    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });
});

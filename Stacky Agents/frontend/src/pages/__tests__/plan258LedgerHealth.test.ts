/**
 * Plan 258 F3 — tests del núcleo PURO de la tarjeta "Salud de ledgers".
 *
 * Correr:
 *   npx vitest run src/pages/__tests__/plan258LedgerHealth.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  buildLedgerRows,
  hayAlgoQueReportar,
  ledgerLabel,
  resumenDeSalud,
  textoDeLimpieza,
  type LedgerHealthPayload,
  type LedgerHealthRow,
} from "../../components/ledgerHealthModel";

function fila(p: Partial<LedgerHealthRow>): LedgerHealthRow {
  return {
    name: "ci_runs",
    total: 0,
    prod: 0,
    test: 0,
    unknown: 0,
    purgeable: true,
    deletable: 0,
    confirm_token: null,
    ...p,
  };
}

/** La foto REAL medida antes del plan. */
const MEDIDO: LedgerHealthPayload = {
  ok: true,
  purge_enabled: false,
  deletable_total: 18,
  orphans: [],
  ledgers: [
    fila({ name: "ci_runs", total: 8, test: 8, deletable: 8 }),
    fila({ name: "env_applies", total: 10, test: 10, deletable: 10 }),
    fila({ name: "db_query_audit", total: 9, unknown: 9, purgeable: false }),
    fila({ name: "config_transfer_events", total: 444, unknown: 444, purgeable: false }),
    fila({ name: "build_runs", total: 5, unknown: 5, purgeable: false }),
  ],
};

describe("buildLedgerRows", () => {
  it("ordena por cantidad de líneas de prueba, primero lo más contaminado", () => {
    const filas = buildLedgerRows(MEDIDO);
    expect(filas.map((f) => f.name)).toEqual([
      "env_applies",
      "ci_runs",
      "config_transfer_events",
      "db_query_audit",
      "build_runs",
    ]);
  });

  it("descarta los archivos vacíos: no aportan nada y harían ruido", () => {
    const filas = buildLedgerRows({
      ok: true,
      ledgers: [fila({ name: "ci_runs", total: 0 }), fila({ name: "build_runs", total: 3 })],
    });
    expect(filas.map((f) => f.name)).toEqual(["build_runs"]);
  });

  it("no rompe con respuesta nula, vacía o de un servidor viejo", () => {
    expect(buildLedgerRows(null)).toEqual([]);
    expect(buildLedgerRows(undefined)).toEqual([]);
    expect(buildLedgerRows({})).toEqual([]);
    expect(buildLedgerRows({ ok: false })).toEqual([]);
    expect(buildLedgerRows({ ok: true, ledgers: null })).toEqual([]);
  });
});

describe("hayAlgoQueReportar", () => {
  it("con la contaminación medida, la tarjeta se muestra", () => {
    expect(hayAlgoQueReportar(MEDIDO)).toBe(true);
  });

  it("líneas de procedencia desconocida NO son un problema", () => {
    // Son el estado honesto de lo histórico y se extinguen solas. Alarmar por
    // ellas sería alarmar para siempre.
    const soloUnknown: LedgerHealthPayload = {
      ok: true,
      orphans: [],
      ledgers: [
        fila({ name: "config_transfer_events", total: 444, unknown: 444, purgeable: false }),
        fila({ name: "db_query_audit", total: 9, unknown: 9, purgeable: false }),
      ],
    };
    expect(hayAlgoQueReportar(soloUnknown)).toBe(false);
  });

  it("una corrida real sin cerrar alcanza para mostrarla", () => {
    expect(
      hayAlgoQueReportar({
        ok: true,
        ledgers: [fila({ name: "ci_runs", total: 3, prod: 3 })],
        orphans: [
          {
            project: "RSPACIFICO",
            tracker_type: "ado",
            pipeline_id: "77",
            ref: "main",
            web_url: null,
            triggered_at: "2026-07-25T00:00:00+00:00",
            age_hours: 48.2,
          },
        ],
      })
    ).toBe(true);
  });

  it("todo limpio: la tarjeta no se renderiza", () => {
    expect(
      hayAlgoQueReportar({
        ok: true,
        orphans: [],
        ledgers: [fila({ name: "ci_runs", total: 5, prod: 5 })],
      })
    ).toBe(false);
    expect(hayAlgoQueReportar(null)).toBe(false);
  });
});

describe("textoDeLimpieza", () => {
  it("dice qué se borra, qué NO se toca y que hay copia", () => {
    const texto = textoDeLimpieza(
      fila({ name: "ci_runs", total: 20, test: 8, prod: 5, unknown: 7, deletable: 8 })
    );
    expect(texto).toContain("Se eliminarán 8 líneas de prueba de ci_runs.jsonl");
    expect(texto).toContain("Las 5 de producción");
    expect(texto).toContain("7 de procedencia desconocida NO se tocan");
    expect(texto).toContain("Se guarda una copia antes");
  });

  it("concuerda el singular", () => {
    const texto = textoDeLimpieza(fila({ deletable: 1 }));
    expect(texto).toContain("Se eliminarán 1 línea de prueba");
  });
});

describe("resumenDeSalud y ledgerLabel", () => {
  it("resume la verdad medida", () => {
    expect(resumenDeSalud(MEDIDO)).toBe("18 de 476 líneas las escribió una prueba");
  });

  it("suma las corridas sin cerrar cuando las hay", () => {
    const resumen = resumenDeSalud({
      ok: true,
      ledgers: [fila({ name: "ci_runs", total: 10, test: 2, prod: 8 })],
      orphans: [
        {
          project: "P",
          tracker_type: "ado",
          pipeline_id: "1",
          ref: null,
          web_url: null,
          triggered_at: null,
          age_hours: 30,
        },
      ],
    });
    expect(resumen).toBe("2 de 10 líneas las escribió una prueba · 1 corrida real sin cerrar");
  });

  it("traduce el nombre técnico y deja pasar el desconocido", () => {
    expect(ledgerLabel("ci_runs")).toBe("Corridas de integración continua");
    expect(ledgerLabel("env_applies")).toBe("Aplicaciones de entorno");
    expect(ledgerLabel("un_ledger_futuro")).toBe("un_ledger_futuro");
  });
});

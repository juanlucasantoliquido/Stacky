/**
 * Plan 257 F3 — tests del núcleo PURO de la tarjeta de firmas ruidosas.
 *
 * Correr POR ARCHIVO y con ruta concreta (el glob `src/**` no se expande en
 * PowerShell y la corrida completa contamina cross-file):
 *   npx vitest run src/components/__tests__/logNoiseModel.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  buildLogNoiseRows,
  logNoiseLabel,
  LOG_NOISE_TOP,
  type LogNoiseSignature,
} from "../logNoiseModel";

function firma(n: number, suppressed: number): LogNoiseSignature {
  return {
    signature: `stacky.mod${n}|30|mensaje N numero ${n}`,
    logger: `stacky.mod${n}`,
    level: "WARNING",
    count: suppressed + 1,
    suppressed,
    first_seen: "2026-07-27T09:00:00+00:00",
    last_seen: "2026-07-27T09:10:00+00:00",
  };
}

describe("buildLogNoiseRows", () => {
  it("test_devuelve_vacio_sin_firmas", () => {
    expect(buildLogNoiseRows(null)).toEqual([]);
    expect(buildLogNoiseRows(undefined)).toEqual([]);
    expect(buildLogNoiseRows({ enabled: true, signatures: [] })).toEqual([]);
    expect(buildLogNoiseRows({ enabled: true, signatures: null })).toEqual([]);
    // Agrupado apagado: 200 con enabled=false, la tarjeta no se dibuja.
    expect(buildLogNoiseRows({ enabled: false, signatures: [firma(1, 9)] })).toEqual([]);
    // Tarjeta apagada por el operador: hay dato, pero no se dibuja.
    expect(
      buildLogNoiseRows({ enabled: true, card_enabled: false, signatures: [firma(1, 9)] })
    ).toEqual([]);
    // Servidor viejo que no manda `card_enabled`: la tarjeta SI se dibuja.
    expect(buildLogNoiseRows({ enabled: true, signatures: [firma(1, 9)] })).toHaveLength(1);
  });

  it("test_ordena_por_suppressed_y_corta_en_10", () => {
    const entrada = Array.from({ length: 15 }, (_, i) => firma(i, i));
    const filas = buildLogNoiseRows({ enabled: true, signatures: entrada });

    expect(filas).toHaveLength(LOG_NOISE_TOP);
    expect(filas[0].suppressed).toBe(14);
    expect(filas[9].suppressed).toBe(5);
    // No muta la respuesta original.
    expect(entrada[0].suppressed).toBe(0);
  });
});

describe("logNoiseLabel", () => {
  it("saca el prefijo tecnico de logger y nivel", () => {
    expect(logNoiseLabel("stacky.config|30|agents_dir no existe: <PATH>")).toBe(
      "agents_dir no existe: <PATH>"
    );
    expect(logNoiseLabel("sin-formato")).toBe("sin-formato");
  });
});

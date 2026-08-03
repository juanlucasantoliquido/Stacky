import { describe, it, expect } from "vitest";
import { debeRefrescarCatalogo } from "../modelCatalogRefresh";

/** Plan 288 F9.1 — los 6 casos. La regla existe para que esto NO sea un sondeo. */

const TTL = 300_000;

describe("Plan 288 F9.1 — cuándo corresponde volver a pedir el catálogo", () => {
  it("refresco_no_si_la_pestana_esta_oculta", () => {
    // Aunque esté requetevencido: con la pestaña oculta no se pide nunca.
    expect(debeRefrescarCatalogo(false, 1_000, 9_999_999, TTL)).toBe(false);
    expect(debeRefrescarCatalogo(false, 0, 9_999_999, TTL)).toBe(false);
  });

  it("refresco_no_antes_del_tiempo_de_vida", () => {
    expect(debeRefrescarCatalogo(true, 1_000, 1_000 + TTL - 1, TTL)).toBe(false);
  });

  it("refresco_si_visible_y_vencido", () => {
    expect(debeRefrescarCatalogo(true, 1_000, 1_000 + TTL, TTL)).toBe(true);
    expect(debeRefrescarCatalogo(true, 1_000, 1_000 + TTL + 1, TTL)).toBe(true);
  });

  it("refresco_si_nunca_se_pidio", () => {
    expect(debeRefrescarCatalogo(true, 0, 0, TTL)).toBe(true);
  });

  it("refresco_tolera_reloj_hacia_atras", () => {
    // Cambio de hora o suspensión: se trata como vencido (lado seguro).
    expect(debeRefrescarCatalogo(true, 900_000, 1_000, TTL)).toBe(true);
  });

  it("refresco_no_dispara_dos_veces_seguidas", () => {
    // Simula el ciclo real: se pide, se marca el momento, y volver a la pestaña
    // enseguida NO vuelve a pedir.
    const ahora = 5_000_000;
    expect(debeRefrescarCatalogo(true, ahora - TTL, ahora, TTL)).toBe(true);
    const pedidoEn = ahora;              // el hook marca el momento del pedido
    expect(debeRefrescarCatalogo(true, pedidoEn, ahora + 1, TTL)).toBe(false);
    expect(debeRefrescarCatalogo(true, pedidoEn, ahora + 1_000, TTL)).toBe(false);
  });
});

// Plan 295 F10 — el intervalo de auto-sync sale del backend (flag del operador),
// con el 45 000 historico como fallback.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { intervaloDeSync } from "../ticketSyncIntervalo";

const PAGES = resolve(dirname(fileURLToPath(import.meta.url)), "..");

describe("plan 295 F10 — el intervalo es del operador", () => {
  it("con 180000 del backend devuelve 180000, no la constante", () => {
    expect(intervaloDeSync(180000, 45000)).toBe(180000);
  });

  it("con undefined (endpoint caido) devuelve el fallback", () => {
    expect(intervaloDeSync(undefined, 45000)).toBe(45000);
    expect(intervaloDeSync(null, 45000)).toBe(45000);
  });

  it("con 0, negativo o NaN devuelve el fallback (un 0 seria un bucle de red)", () => {
    expect(intervaloDeSync(0, 45000)).toBe(45000);
    expect(intervaloDeSync(-1, 45000)).toBe(45000);
    expect(intervaloDeSync(Number.NaN, 45000)).toBe(45000);
  });

  it("los DOS consumidores de TicketBoard usan la MISMA variable", () => {
    // Si solo se alimentara el hook, SyncStatusBar derivaria "stale" contra 45 s
    // mientras el sync corre cada 180 s: el operador veria la barra en rojo
    // permanente. Es un test de texto fuente porque lo que hay que garantizar es
    // que las dos lineas salgan de la misma fuente.
    const t = readFileSync(resolve(PAGES, "TicketBoard.tsx"), "utf-8");
    expect(t).toContain("intervalMs: intervaloSync");
    expect(t).toContain("intervalMs={intervaloSync}");
  });
});

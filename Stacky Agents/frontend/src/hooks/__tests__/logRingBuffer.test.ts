/**
 * Plan 156 F3 — Tests del ring-buffer puro (sin DOM).
 */
import { describe, it, expect } from "vitest";
import type { LogLine } from "../../types";
import { appendBounded, emptyRing, LOG_RING_CAP } from "../logRingBuffer";

function line(i: number, message?: string): LogLine {
  return { timestamp: String(i), level: "info", message: message ?? `msg-${i}` };
}

describe("logRingBuffer (plan 156 F3)", () => {
  it("test_cota_20000_lineas: acota lines y seen a 5000, dropped=15000", () => {
    let ring = emptyRing();
    for (let i = 0; i < 20000; i++) ring = appendBounded(ring, line(i));
    expect(ring.lines.length).toBe(LOG_RING_CAP);
    expect(ring.lines.length).toBe(5000);
    expect(ring.seen.size).toBe(5000);
    expect(ring.dropped).toBe(15000);
    // La cola conserva las últimas 5000 (msg-15000 .. msg-19999)
    expect(ring.lines[0].message).toBe("msg-15000");
    expect(ring.lines[ring.lines.length - 1].message).toBe("msg-19999");
  });

  it("test_dedup_en_ventana: la misma línea dos veces es no-op (mismo objeto)", () => {
    const ring0 = emptyRing();
    const ring1 = appendBounded(ring0, line(1));
    const ring2 = appendBounded(ring1, line(1)); // duplicado en ventana
    expect(ring2).toBe(ring1); // MISMO objeto → no-op
    expect(ring2.lines.length).toBe(1);
  });

  it("test_duplicado_tardio_reentra: A expulsada del ring puede reingresar", () => {
    const cap = 3;
    let ring = emptyRing();
    const A = line(0, "A");
    ring = appendBounded(ring, A, cap);
    // Llenar hasta expulsar A (insertar 3 líneas nuevas)
    ring = appendBounded(ring, line(1), cap);
    ring = appendBounded(ring, line(2), cap);
    ring = appendBounded(ring, line(3), cap);
    // A ya salió de ventana → su clave no está en seen
    expect(ring.lines.some((l) => l.message === "A")).toBe(false);
    // Reinsertar A: como su clave salió de seen, reingresa (no es no-op)
    const after = appendBounded(ring, A, cap);
    expect(after).not.toBe(ring);
    expect(after.lines[after.lines.length - 1].message).toBe("A");
  });

  it("test_cap_configurable: cap=3 con 5 inserciones → lines=3, dropped=2, seen=3", () => {
    let ring = emptyRing();
    for (let i = 0; i < 5; i++) ring = appendBounded(ring, line(i), 3);
    expect(ring.lines.length).toBe(3);
    expect(ring.dropped).toBe(2);
    expect(ring.seen.size).toBe(3);
  });
});

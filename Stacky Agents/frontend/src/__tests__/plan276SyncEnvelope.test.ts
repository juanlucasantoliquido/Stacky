/**
 * Plan 276 F6 — el envelope del sync deja de ser un falso verde, y un sync MANUAL
 * siempre refetchea.
 *
 * Los dos defectos que estos 8 casos gatean:
 *  1. `capability_unavailable_envelope` devuelve `{ok:true, available:false}` y el
 *     hook lo tomaba por la rama de éxito ⇒ "sincronizado hace 2s", cero tickets y
 *     cero error. Una carencia DECLARADA no es un éxito.
 *  2. `shouldRefreshTicketQueries` no refetacheaba cuando el backend respondía
 *     `idempotent:true`. En el estreno de GitLab ése es justo el caso del reintento
 *     manual: las filas YA están en la BD y la pantalla se queda vacía. Era un
 *     CLOSURE dentro del hook (sin export) ⇒ intesteable sin RTL, y en este repo no
 *     hay RTL ni jsdom. Extraerlo a nivel de módulo es el 80 % del valor del cambio.
 */
import { describe, it, expect } from "vitest";
import {
  clasificarRespuestaDeSync,
  debeRefrescarQueriesDeTickets,
} from "../hooks/useTicketSync";

describe("plan 276 F6 — clasificarRespuestaDeSync", () => {
  it("ok con synced_at es un éxito", () => {
    expect(
      clasificarRespuestaDeSync({ ok: true, synced_at: "2026-07-31T12:00:00Z" })
    ).toBe("exito");
  });

  it("available:false es CARENCIA aunque venga con ok:true (el falso verde)", () => {
    expect(clasificarRespuestaDeSync({ ok: true, available: false })).toBe("carencia");
  });

  it("rate_limited no es error: solo hay que esperar", () => {
    expect(clasificarRespuestaDeSync({ error: "rate_limited" })).toBe("rate_limited");
  });

  it("ok:false con mensaje es error", () => {
    expect(clasificarRespuestaDeSync({ ok: false, message: "boom" })).toBe("error");
  });
});

describe("plan 276 F6/C3 — debeRefrescarQueriesDeTickets", () => {
  it("un sync MANUAL refetchea aunque el backend responda idempotente", () => {
    // GATE CONTRA EL DEFECTO: con el closure viejo esto devolvía false y el
    // operador se quedaba con la pantalla vacía y los tickets en la base.
    expect(debeRefrescarQueriesDeTickets({ idempotent: true }, "manual")).toBe(true);
  });

  it("el auto_poll idempotente NO refetchea (no se rompe el ahorro de re-renders)", () => {
    expect(debeRefrescarQueriesDeTickets({ idempotent: true }, "auto_poll")).toBe(false);
  });

  it("un sync MANUAL con contadores en cero también refetchea", () => {
    expect(
      debeRefrescarQueriesDeTickets({ created: 0, updated: 0, removed: 0 }, "manual")
    ).toBe(true);
  });

  it("el auto_poll con filas creadas refetchea, como hoy", () => {
    expect(debeRefrescarQueriesDeTickets({ created: 3 }, "auto_poll")).toBe(true);
  });
});

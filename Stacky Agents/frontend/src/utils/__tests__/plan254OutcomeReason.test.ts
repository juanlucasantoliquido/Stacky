import { describe, expect, it } from "vitest";
import {
  OUTCOME_REASON_LABELS,
  describeOutcomeReason,
  dirtyCloseNotice,
} from "../outcomeReason";

describe("outcomeReason (plan 254 F4)", () => {
  it("mapea los 9 reasons a etiqueta", () => {
    const reasons = [
      "clean_exit",
      "dirty_exit_after_work",
      "quota_exhausted",
      "stall_after_work",
      "stall_no_work",
      "preflight_blocked",
      "reaper_timeout",
      "reaper_heartbeat",
      "cli_failure",
    ];
    // Ni una clave de más: el mapa de la UI tiene EXACTAMENTE 9 entradas.
    expect(Object.keys(OUTCOME_REASON_LABELS)).toHaveLength(9);
    for (const reason of reasons) {
      const d = describeOutcomeReason(reason);
      expect(d, reason).not.toBeNull();
      expect(d!.label.length, reason).toBeGreaterThan(0);
      expect(["exito", "atencion", "espera", "error"], reason).toContain(d!.tone);
      // Ninguno cae en un default genérico.
      expect(d!.label, reason).not.toBe(reason);
    }
    // Los tonos discriminan: entregar trabajo no es lo mismo que fallar.
    expect(OUTCOME_REASON_LABELS.clean_exit.tone).toBe("exito");
    expect(OUTCOME_REASON_LABELS.dirty_exit_after_work.tone).toBe("atencion");
    expect(OUTCOME_REASON_LABELS.quota_exhausted.tone).toBe("espera");
    expect(OUTCOME_REASON_LABELS.cli_failure.tone).toBe("error");
  });

  it("reason desconocido no rompe la ui", () => {
    const d = describeOutcomeReason("reason_del_futuro");
    expect(d).not.toBeNull();
    expect(d!.label).toBe("reason_del_futuro");
    expect(d!.label).not.toBe("undefined");
    expect(describeOutcomeReason(null)).toBeNull();
    expect(describeOutcomeReason(undefined)).toBeNull();
    expect(describeOutcomeReason("")).toBeNull();
  });

  it("blocked_downgrade con pending_review produce el badge de cierre sucio", () => {
    const msg = dirtyCloseNotice({
      blocked_downgrade: {
        from: "completed",
        to: "error",
        pending_review: true,
        kind: "dirty_close_preserved_success",
      },
    });
    expect(msg).not.toBeNull();
    expect(msg).toContain("Cierre sucio, estado preservado");
    expect(msg).toContain("completed");
    expect(msg).toContain("error");

    // El campo plano del payload de /api/executions también lo enciende.
    expect(dirtyCloseNotice({ dirty_close_pending_review: true })).toContain(
      "Cierre sucio, estado preservado",
    );
    // Sin la marca no hay aviso: no se molesta al operador de gratis.
    expect(dirtyCloseNotice({ blocked_downgrade: { from: "running", to: "error" } })).toBeNull();
    expect(dirtyCloseNotice(null)).toBeNull();
    expect(dirtyCloseNotice({})).toBeNull();
  });
});

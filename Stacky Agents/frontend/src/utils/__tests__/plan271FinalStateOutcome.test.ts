// frontend/src/utils/__tests__/plan271FinalStateOutcome.test.ts
// Plan 271 F6 — módulo puro finalStateOutcome.ts. Sin @testing-library/react
// ni jsdom (no están instalados): se prueba el mapa, no un render.
import { describe, expect, it } from "vitest";
import {
  describeFinalState,
  FINAL_STATE_REASON_LABELS,
  type FinalStateTone,
} from "../finalStateOutcome";

describe("describeFinalState", () => {
  it("devuelve null sin outcome", () => {
    expect(describeFinalState(null)).toBeNull();
    expect(describeFinalState(undefined)).toBeNull();
  });

  it("devuelve null cuando el objeto no trae reason", () => {
    expect(describeFinalState({})).toBeNull();
  });

  it("incluye el estado destino cuando reason es 'ok'", () => {
    const r = describeFinalState({ reason: "ok", to: "To Do" });
    expect(r).not.toBeNull();
    expect(r!.label).toContain("To Do");
    expect(r!.tone).toBe("exito");
  });

  it("no_config tiene tono atencion y accion no vacia", () => {
    const r = describeFinalState({ reason: "no_config" });
    expect(r).not.toBeNull();
    expect(r!.tone).toBe("atencion");
    expect(r!.action).not.toHaveLength(0);
  });

  it("un reason futuro/desconocido no rompe: string crudo, tono neutro", () => {
    const r = describeFinalState({ reason: "inventado_futuro" });
    expect(r).toEqual({ label: "inventado_futuro", tone: "atencion", action: "" });
  });

  it("estructural: toda entrada tiene label no vacío y tone válido", () => {
    const tonosValidos: FinalStateTone[] = ["exito", "atencion", "espera", "error"];
    for (const [key, entry] of Object.entries(FINAL_STATE_REASON_LABELS)) {
      expect(entry.label.length, `${key}: label vacío`).toBeGreaterThan(0);
      expect(tonosValidos, `${key}: tone inválido`).toContain(entry.tone);
    }
  });
});

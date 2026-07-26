/**
 * Plan 209 F4 — tests de la lógica PURA del pane.
 *
 * Nota honesta: este repo NO tiene `@testing-library/react` ni `jsdom` (solo
 * `vitest`), así que el render del componente React NO es automatizable acá.
 * El gate del componente es `npx tsc --noEmit` + smoke manual, tal como en los
 * planes de UX previos. Lo que SÍ se testea de verdad es `readValidationPlaybook`,
 * que es la puerta de entrada del pane y donde vive el guard de `disabled` y la
 * retrocompatibilidad con ejecuciones viejas.
 */
import { describe, expect, it } from "vitest";

import { readValidationPlaybook } from "../ValidationPlaybookPane";

describe("readValidationPlaybook", () => {
  it("devuelve null si no hay metadata (ejecuciones viejas)", () => {
    expect(readValidationPlaybook(undefined)).toBeNull();
    expect(readValidationPlaybook(null)).toBeNull();
    expect(readValidationPlaybook({})).toBeNull();
  });

  it("devuelve null si el status es disabled (flag off / agente no user-facing)", () => {
    expect(
      readValidationPlaybook({
        validation_playbook: { status: "disabled", steps: [], sources: [], confidence: 0 },
      }),
    ).toBeNull();
  });

  it("normaliza un playbook enriched", () => {
    const pb = readValidationPlaybook({
      validation_playbook: {
        status: "enriched",
        steps: [{ n: 1, action: "Entrar", expected_result: "Se abre", source: "func-docs:x" }],
        sources: ["func-docs:x"],
        confidence: 0.7,
        degraded_reason: null,
      },
    });

    expect(pb).not.toBeNull();
    expect(pb!.status).toBe("enriched");
    expect(pb!.steps).toHaveLength(1);
    expect(pb!.steps[0].source).toBe("func-docs:x");
    expect(pb!.confidence).toBe(0.7);
  });

  it("es defensivo con shapes rotos", () => {
    const pb = readValidationPlaybook({
      validation_playbook: { status: "degraded", steps: "no soy lista", confidence: "alta" },
    });

    expect(pb!.status).toBe("degraded");
    expect(pb!.steps).toEqual([]);
    expect(pb!.sources).toEqual([]);
    expect(pb!.confidence).toBe(0);
    expect(pb!.degraded_reason).toBeNull();
  });

  it("ignora metadata que no es objeto", () => {
    expect(readValidationPlaybook({ validation_playbook: "texto" })).toBeNull();
    expect(readValidationPlaybook({ validation_playbook: 42 })).toBeNull();
  });
});

// Plan 216 F2/F3 — Lógica de la pestaña Estados.
import { describe, it, expect } from "vitest";
import {
  ROLE_LABEL,
  STATE_ROLES,
  coherenceMessage,
  incoherentStatesFor,
  missingRequiredFields,
  optionsWithCurrent,
  withStatesAdded,
  type FlowRule,
} from "../statesConfigModel";

function regla(ado_state: string, agent_type: string, id = ado_state): FlowRule {
  return { id, ado_state, agent_type };
}

describe("optionsWithCurrent", () => {
  it("agrega el valor guardado si el tracker ya no lo lista", () => {
    // Si no, abrir el dropdown le borraría al operador algo que sí configuró.
    expect(optionsWithCurrent(["A", "B"], "VIEJO")).toEqual(["VIEJO", "A", "B"]);
  });

  it("no duplica si ya está", () => {
    expect(optionsWithCurrent(["A", "B"], "A")).toEqual(["A", "B"]);
  });

  it("sin valor actual devuelve la lista tal cual", () => {
    expect(optionsWithCurrent(["A"], "")).toEqual(["A"]);
    expect(optionsWithCurrent(null, null)).toEqual([]);
  });
});

describe("incoherentStatesFor", () => {
  it("detecta un estado que la regla manda pero el rol no atiende", () => {
    const faltantes = incoherentStatesFor(
      "technical",
      [regla("Technical review", "technical")],
      { input_states: ["Otro"] }
    );

    expect(faltantes).toEqual(["Technical review"]);
  });

  it("no marca nada cuando el rol sí lo declara", () => {
    expect(incoherentStatesFor(
      "technical",
      [regla("Technical review", "technical")],
      { input_states: ["Technical review"] }
    )).toEqual([]);
  });

  it("compara sin distinguir mayúsculas ni espacios", () => {
    expect(incoherentStatesFor(
      "technical",
      [regla("  technical REVIEW ", "technical")],
      { input_states: ["Technical review"] }
    )).toEqual([]);
  });

  it("ignora las reglas de otros roles", () => {
    expect(incoherentStatesFor(
      "technical",
      [regla("Functional review", "functional")],
      { input_states: [] }
    )).toEqual([]);
  });

  it("no repite el mismo estado dos veces", () => {
    const faltantes = incoherentStatesFor(
      "technical",
      [regla("X", "technical", "r1"), regla("x", "technical", "r2")],
      { input_states: [] }
    );

    expect(faltantes).toEqual(["X"]);
  });

  it("tolera entradas nulas", () => {
    expect(incoherentStatesFor("technical", null, null)).toEqual([]);
  });
});

describe("withStatesAdded", () => {
  it("agrega los faltantes sin tocar el original", () => {
    const original = { input_states: ["A"], next_state_ok: "B" };

    const nuevo = withStatesAdded(original, ["C"]);

    expect(nuevo.input_states).toEqual(["A", "C"]);
    expect(nuevo.next_state_ok).toBe("B");
    expect(original.input_states).toEqual(["A"]);
  });

  it("no duplica lo que ya estaba", () => {
    expect(withStatesAdded({ input_states: ["A"] }, ["a", "A"]).input_states)
      .toEqual(["A"]);
  });

  it("desde una máquina vacía funciona igual", () => {
    expect(withStatesAdded(null, ["A"]).input_states).toEqual(["A"]);
  });
});

describe("coherenceMessage", () => {
  it("sin faltantes no dice nada", () => {
    expect(coherenceMessage([])).toBeNull();
  });

  it("singular y plural", () => {
    expect(coherenceMessage(["A"])).toContain('"A"');
    expect(coherenceMessage(["A", "B"])).toContain("A, B");
  });
});

describe("missingRequiredFields", () => {
  it("un rol sin next_state_ok no puede cerrar el ticket", () => {
    expect(missingRequiredFields({ input_states: ["A"] }))
      .toEqual(["estado al terminar OK"]);
  });

  it("sin estados de entrada tampoco arranca", () => {
    expect(missingRequiredFields({ next_state_ok: "B" }))
      .toEqual(["estados de entrada"]);
  });

  it("completo no falta nada", () => {
    expect(missingRequiredFields({ input_states: ["A"], next_state_ok: "B" }))
      .toEqual([]);
  });

  it("vacío falta todo", () => {
    expect(missingRequiredFields(null)).toHaveLength(2);
  });
});

describe("roles", () => {
  it("son los tres de siempre, con etiqueta en castellano", () => {
    expect(STATE_ROLES).toEqual(["functional", "technical", "developer"]);
    for (const r of STATE_ROLES) expect(ROLE_LABEL[r]).toBeTruthy();
  });
});

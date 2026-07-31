/**
 * plan277JerarquiaLocal.test.ts — Plan 277 F4, lado frontend.
 *
 * Cubre la lógica que decide si el operador VE el control y la que valida el número
 * del ticket padre antes de mandarlo. Es todo lo verificable de esta superficie: sin
 * RTL ni jsdom en el repo, el render se cubre con el smoke manual del plan.
 */
import { describe, it, expect } from "vitest";
import {
  TIPOS_CANONICOS_JERARQUIA,
  debeMostrarControlJerarquia,
  rotuloDeTipo,
  validarPadre,
  valorInicialPadre,
} from "../lib/jerarquiaLocal";

const GITLAB = {
  ado_id: 7,
  tracker_type: "gitlab",
  local_work_item_type: null,
  local_parent_iid: null,
};

describe("Plan 277 F4 — ¿se muestra el control de jerarquía local?", () => {
  it("caso 1: sí, en un ticket de GitLab con la clave presente y la flag encendida", () => {
    expect(debeMostrarControlJerarquia(GITLAB, true)).toBe(true);
    // Y con un valor ya cargado también (no depende de que esté vacío).
    expect(
      debeMostrarControlJerarquia({ ...GITLAB, local_work_item_type: "Epic" }, true),
    ).toBe(true);
  });

  it("caso 2: NO cuando la clave `local_work_item_type` no viene en el payload", () => {
    // Es el payload legacy de 16 claves (plan 218 F5) que devuelve `to_dict()` con
    // STACKY_CANONICAL_VOCABULARY_ENABLED apagada. Sin la clave, el control abriría
    // vacío y al guardar pisaría con null lo que el operador ya tenía.
    const legacy = { ado_id: 7, tracker_type: "gitlab" };
    // POSITIVO SEMBRADO PRIMERO: el mismo ticket CON la clave sí se muestra, así
    // este `false` no puede venir de otra condición.
    expect(debeMostrarControlJerarquia({ ...legacy, local_work_item_type: null }, true)).toBe(true);
    expect(debeMostrarControlJerarquia(legacy, true)).toBe(false);
    // `null` es un valor legítimo ("sin clasificar"), no una clave ausente.
    expect(Object.prototype.hasOwnProperty.call(legacy, "local_work_item_type")).toBe(false);
  });

  it("caso 3: NO en un proyecto que no es GitLab, ni con la flag apagada", () => {
    expect(debeMostrarControlJerarquia({ ...GITLAB, tracker_type: "azure_devops" }, true)).toBe(false);
    expect(debeMostrarControlJerarquia(GITLAB, false)).toBe(false);
    expect(debeMostrarControlJerarquia(null, true)).toBe(false);
    // El tracker se compara sin distinguir mayúsculas: el alta lo escribe el operador.
    expect(debeMostrarControlJerarquia({ ...GITLAB, tracker_type: "GitLab" }, true)).toBe(true);
  });
});

describe("Plan 277 F4 — validación del número del ticket padre", () => {
  it("caso 4: acepta un entero positivo y rechaza cero, negativo y no numérico", () => {
    expect(validarPadre("42", GITLAB)).toEqual({ ok: true, valor: 42 });
    expect(validarPadre(42, GITLAB)).toEqual({ ok: true, valor: 42 });
    expect(validarPadre("  42  ", GITLAB)).toEqual({ ok: true, valor: 42 });

    expect(validarPadre("0", GITLAB)).toMatchObject({ ok: false, codigo: "no_positivo" });
    expect(validarPadre("-3", GITLAB)).toMatchObject({ ok: false, codigo: "no_positivo" });
    expect(validarPadre("3.5", GITLAB)).toMatchObject({ ok: false, codigo: "no_entero" });
    expect(validarPadre("ADO-42", GITLAB)).toMatchObject({ ok: false, codigo: "no_entero" });

    // Vacío NO es un error: es el borrado de la clasificación local (manda null).
    expect(validarPadre("", GITLAB)).toEqual({ ok: true, valor: null });
    expect(validarPadre(null, GITLAB)).toEqual({ ok: true, valor: null });
  });

  it("caso 5: rechaza el auto-padre, que es el que tumba el grafo con un 500", () => {
    // POSITIVO SEMBRADO: otro número sí pasa, así el rechazo no es "rechaza todo".
    expect(validarPadre("8", GITLAB)).toEqual({ ok: true, valor: 8 });

    const r = validarPadre("7", GITLAB); // 7 === GITLAB.ado_id
    expect(r).toMatchObject({ ok: false, codigo: "auto_padre" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.mensaje).toContain("sí mismo");
  });
});

describe("Plan 277 F4 — catálogo de tipos y precarga", () => {
  it("caso 6: son los 8 canónicos del contrato del servidor, con rótulo visible", () => {
    // Los VALORES tienen que coincidir exactamente con TIPOS_CANONICOS de
    // backend/services/gitlab_hierarchy.py: son los que viajan en el PATCH.
    expect(TIPOS_CANONICOS_JERARQUIA.map((t) => t.valor)).toEqual([
      "Epic", "Funcional", "Tecnico", "Implementacion",
      "Bug", "Task", "Feature", "Issue",
    ]);
    expect(new Set(TIPOS_CANONICOS_JERARQUIA.map((t) => t.rotulo)).size).toBe(8);
    expect(rotuloDeTipo("Epic")).toBe("Épica");
    // Regla 5 del contrato: lo desconocido no se descarta, se muestra tal cual.
    expect(rotuloDeTipo("User Story")).toBe("User Story");
    expect(rotuloDeTipo(null)).toBe("");

    // Precarga: el control abre con lo que el operador ya guardó (echo-back).
    expect(valorInicialPadre({ ...GITLAB, local_parent_iid: 42 })).toBe("42");
    expect(valorInicialPadre(GITLAB)).toBe("");
  });
});

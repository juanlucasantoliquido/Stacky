/**
 * plan277JerarquiaLocal.test.ts — Plan 277 F4, lado frontend.
 *
 * Cubre la lógica que decide si el operador VE el control y la que valida el número
 * del ticket padre antes de mandarlo. Es todo lo verificable de esta superficie: sin
 * RTL ni jsdom en el repo, el render se cubre con el smoke manual del plan.
 */
import { describe, it, expect } from "vitest";
import {
  FLAG_PUBLICAR_ETIQUETAS,
  TIPOS_CANONICOS_JERARQUIA,
  alternarSeleccion,
  debeMostrarControlJerarquia,
  esPublicable,
  estadoBotonPublicar,
  resumenBackfill,
  rotuloDeTipo,
  seleccionInicialBackfill,
  validarPadre,
  valorInicialPadre,
  type CambioBackfill,
  type PlanBackfill,
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

// ── Plan 277 F5 — publicar las etiquetas EN GitLab ──────────────────────────

const _c = (over: Partial<CambioBackfill>): CambioBackfill => ({
  ado_id: 1,
  iid: 1,
  title: "t",
  url: "u",
  agregar: [],
  ya_tiene: [],
  conflicto: false,
  ...over,
});

const PLAN: PlanBackfill = {
  proyecto: "RIPLEY",
  total: 4,
  cambios: [
    _c({ ado_id: 10, iid: 10, agregar: ["type::epic"] }),                    // publicable
    _c({ ado_id: 11, iid: 11, conflicto: true, ya_tiene: ["type::bug"] }),   // GitLab manda
    _c({ ado_id: 12, iid: 12, agregar: [], ya_tiene: ["type::epic"] }),      // ya está
    _c({ ado_id: 13, iid: 13, agregar: ["epic::10"] }),                      // publicable
  ],
  con_conflicto: 1,
};

describe("Plan 277 F5 — qué se puede publicar y qué no", () => {
  it("caso 7: el conflicto y el 'ya está' no son publicables ni preseleccionables", () => {
    // POSITIVO SEMBRADO: los dos que sí tienen algo que agregar pasan.
    expect(esPublicable(PLAN.cambios[0])).toBe(true);
    expect(esPublicable(PLAN.cambios[3])).toBe(true);

    expect(esPublicable(PLAN.cambios[1])).toBe(false);  // conflicto: manda GitLab
    expect(esPublicable(PLAN.cambios[2])).toBe(false);  // idempotencia: nada que agregar
    expect(esPublicable(null)).toBe(false);

    expect(seleccionInicialBackfill(PLAN)).toEqual([10, 13]);
    expect(seleccionInicialBackfill(null)).toEqual([]);

    // Marcar a mano lo que está en conflicto NO lo mete en la selección.
    expect(alternarSeleccion([], PLAN.cambios[1])).toEqual([]);
    expect(alternarSeleccion([], PLAN.cambios[0])).toEqual([10]);
    expect(alternarSeleccion([10, 13], PLAN.cambios[0])).toEqual([13]);

    expect(resumenBackfill(PLAN)).toEqual({
      total: 4, publicables: 2, conflictos: 1, sinCambios: 1,
    });
  });

  it("caso 8: con la flag apagada el botón queda deshabilitado y el aviso la nombra", () => {
    const off = estadoBotonPublicar(false, [10]);
    expect(off.habilitado).toBe(false);
    expect(off.hint).toContain(FLAG_PUBLICAR_ETIQUETAS);
    expect(FLAG_PUBLICAR_ETIQUETAS).toBe("STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED");

    // Encendida pero sin nada elegido: tampoco se puede. "Nunca todos por defecto".
    const vacio = estadoBotonPublicar(true, []);
    expect(vacio.habilitado).toBe(false);
    expect(vacio.hint).toContain("al menos un");

    // Encendida y con selección: recién ahí se habilita, y dice cuántos.
    const on = estadoBotonPublicar(true, [10, 13]);
    expect(on.habilitado).toBe(true);
    expect(on.rotulo).toContain("(2)");
    expect(on.hint).toBe("");

    // Mientras escribe no se puede volver a apretar (evita el doble envío).
    expect(estadoBotonPublicar(true, [10], true).habilitado).toBe(false);
  });
});

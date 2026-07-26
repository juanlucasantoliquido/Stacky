// Plan 175 F3 — Menú contextual (lógica pura).
import { describe, it, expect } from "vitest";
import { armTransition, clampMenuPosition, menuKeydown } from "./contextMenuModel";

describe("clampMenuPosition", () => {
  it("si entra, no se mueve", () => {
    expect(clampMenuPosition(100, 100, 200, 150, 1920, 1080)).toEqual({ left: 100, top: 100 });
  });

  it("si desborda a la derecha, se voltea", () => {
    // Un menú que se sale del viewport tiene la mitad de las acciones
    // inalcanzables.
    expect(clampMenuPosition(1900, 100, 200, 150, 1920, 1080).left).toBe(1700);
  });

  it("si desborda abajo, se voltea", () => {
    expect(clampMenuPosition(100, 1050, 200, 150, 1920, 1080).top).toBe(900);
  });

  it("nunca queda pegado al borde, ni en un viewport enano", () => {
    const p = clampMenuPosition(5, 5, 500, 500, 100, 100);

    expect(p.left).toBeGreaterThanOrEqual(8);
    expect(p.top).toBeGreaterThanOrEqual(8);
  });
});

describe("menuKeydown", () => {
  it("las flechas dan la vuelta", () => {
    // En un menú corto el wrap se agradece; en una lista larga no (por eso el
    // roving del 172 clampea y esto no).
    expect(menuKeydown("ArrowDown", 2, 3)).toEqual({ kind: "move", index: 0 });
    expect(menuKeydown("ArrowUp", 0, 3)).toEqual({ kind: "move", index: 2 });
  });

  it("Home y End van a los extremos", () => {
    expect(menuKeydown("Home", 2, 3)).toEqual({ kind: "move", index: 0 });
    expect(menuKeydown("End", 0, 3)).toEqual({ kind: "move", index: 2 });
  });

  it("Enter y espacio seleccionan; Escape cierra", () => {
    expect(menuKeydown("Enter", 0, 3)).toEqual({ kind: "select" });
    expect(menuKeydown(" ", 0, 3)).toEqual({ kind: "select" });
    expect(menuKeydown("Escape", 0, 3)).toEqual({ kind: "close" });
  });

  it("cualquier otra tecla no hace nada", () => {
    expect(menuKeydown("a", 0, 3)).toEqual({ kind: "none" });
  });

  it("con el menú vacío solo Escape hace algo", () => {
    expect(menuKeydown("Escape", 0, 0)).toEqual({ kind: "close" });
    for (const k of ["ArrowDown", "ArrowUp", "Home", "End", "Enter", " "]) {
      expect(menuKeydown(k, 0, 0)).toEqual({ kind: "none" });
    }
  });
});

describe("armTransition", () => {
  it("una acción segura dispara directo", () => {
    expect(armTransition({ armedId: null }, { type: "activate", id: "a", effect: "safe" })).toEqual({
      state: { armedId: null },
      fire: "a",
    });
  });

  it("una con efecto necesita dos pasos", () => {
    // El primer click arma, el segundo dispara: un click de más no borra nada.
    const primero = armTransition({ armedId: null }, { type: "activate", id: "d", effect: "confirm" });
    expect(primero).toEqual({ state: { armedId: "d" }, fire: null });

    const segundo = armTransition(primero.state, { type: "activate", id: "d", effect: "confirm" });
    expect(segundo).toEqual({ state: { armedId: null }, fire: "d" });
  });

  it("activar OTRO ítem re-arma en vez de disparar", () => {
    // Si disparara, tener uno armado convertiría el próximo click en una acción
    // que nadie pidió.
    expect(armTransition({ armedId: "d" }, { type: "activate", id: "x", effect: "confirm" })).toEqual({
      state: { armedId: "x" },
      fire: null,
    });
  });

  it("una acción segura no se ve afectada por lo armado", () => {
    expect(armTransition({ armedId: "d" }, { type: "activate", id: "a", effect: "safe" })).toEqual({
      state: { armedId: null },
      fire: "a",
    });
  });

  it("escape y cierre desarman sin disparar", () => {
    for (const type of ["escape", "close"] as const) {
      expect(armTransition({ armedId: "d" }, { type })).toEqual({ state: { armedId: null }, fire: null });
    }
  });
});

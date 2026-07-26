// Plan 172 F4 — Roving focus (lógica pura).
import { describe, it, expect } from "vitest";
import { clampRovingIndex, nextRovingIndex, rovingActionForKey } from "./rovingFocus";

describe("rovingActionForKey", () => {
  it("j/k y flechas mueven", () => {
    expect(rovingActionForKey("j", false)).toBe("next");
    expect(rovingActionForKey("ArrowDown", false)).toBe("next");
    expect(rovingActionForKey("k", false)).toBe("prev");
    expect(rovingActionForKey("ArrowUp", false)).toBe("prev");
  });

  it("mayúsculas también: Shift+J no puede quedar muerto", () => {
    expect(rovingActionForKey("J", false)).toBe("next");
    expect(rovingActionForKey("K", false)).toBe("prev");
  });

  it("Home/End, Enter y Escape", () => {
    expect(rovingActionForKey("Home", false)).toBe("first");
    expect(rovingActionForKey("End", false)).toBe("last");
    expect(rovingActionForKey("Enter", false)).toBe("open");
    expect(rovingActionForKey("Escape", false)).toBe("escape");
  });

  it("con modificador NO hace nada, nunca", () => {
    // Ctrl+End y Alt+flecha son del navegador: secuestrarlos rompe algo que el
    // operador ya usa, y encima sin avisar.
    for (const k of ["j", "k", "ArrowDown", "Home", "End", "Enter", "Escape"]) {
      expect(rovingActionForKey(k, true)).toBeNull();
    }
  });

  it("cualquier otra tecla es null: escribir sigue funcionando", () => {
    expect(rovingActionForKey("a", false)).toBeNull();
    expect(rovingActionForKey("Tab", false)).toBeNull();
    expect(rovingActionForKey(" ", false)).toBeNull();
  });
});

describe("nextRovingIndex", () => {
  it("avanza y retrocede de a uno", () => {
    expect(nextRovingIndex("next", 0, 5)).toBe(1);
    expect(nextRovingIndex("prev", 3, 5)).toBe(2);
  });

  it("clampea en los bordes en vez de dar la vuelta", () => {
    // El wraparound hace perder la referencia de dónde se está en una lista larga.
    expect(nextRovingIndex("next", 4, 5)).toBe(4);
    expect(nextRovingIndex("prev", 0, 5)).toBe(0);
  });

  it("sin fila activa, next va a la primera y prev a la última", () => {
    expect(nextRovingIndex("next", -1, 5)).toBe(0);
    expect(nextRovingIndex("prev", -1, 5)).toBe(4);
  });

  it("first y last van a los extremos desde donde sea", () => {
    expect(nextRovingIndex("first", 3, 5)).toBe(0);
    expect(nextRovingIndex("last", 1, 5)).toBe(4);
    expect(nextRovingIndex("last", -1, 5)).toBe(4);
  });

  it("lista vacía devuelve -1, no 0", () => {
    // Devolver 0 apuntaría a una fila que no existe.
    for (const a of ["next", "prev", "first", "last"] as const) {
      expect(nextRovingIndex(a, 0, 0)).toBe(-1);
    }
  });

  it("una sola fila se queda quieta", () => {
    expect(nextRovingIndex("next", 0, 1)).toBe(0);
    expect(nextRovingIndex("prev", 0, 1)).toBe(0);
  });
});

describe("clampRovingIndex", () => {
  it("si la lista encogió, el índice baja al último real", () => {
    // Borrar el último elemento dejaría el foco apuntando a la nada.
    expect(clampRovingIndex(7, 3)).toBe(2);
  });

  it("un índice válido no se toca", () => {
    expect(clampRovingIndex(1, 3)).toBe(1);
  });

  it("lista vacía deja sin activo", () => {
    expect(clampRovingIndex(2, 0)).toBe(-1);
  });

  it("sin activo sigue sin activo aunque haya filas", () => {
    expect(clampRovingIndex(-1, 5)).toBe(-1);
  });
});

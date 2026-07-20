import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../TicketBoard.module.css", import.meta.url), "utf-8");

describe("Plan 150 F4 — TicketBoard migrado a spacing tokens", () => {
  it("consume var(--space-*) en cantidad significativa (≥12) — este es el gate real", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(12);
  });
  it("guard: ningún borde migrado por error (verde también pre-migración, C7)", () => {
    // regla solo-en-escala: 1px no está en el mapa ⇒ no debe tokenizarse
    expect(CSS).not.toContain("border: var(--space-");
  });
});

describe("Plan 150 F4 — fix responsive (las TRES reglas minmax, C2)", () => {
  it("agrega breakpoint 820px que colapsa TODOS los grids que desbordan", () => {
    const flat = CSS.replace(/\s+/g, " ");
    expect(flat).toMatch(/@media \(max-width: 820px\)/);
    const collapsed = (flat.match(/minmax\(0, 1fr\)/g) ?? []).length;
    const floors = (CSS.match(/minmax\(3\d{2}px/g) ?? []).length; // hoy 3 (líneas 156, 992, 1039)
    expect(collapsed).toBeGreaterThanOrEqual(floors);
    expect(floors).toBeGreaterThanOrEqual(3);
  });
});

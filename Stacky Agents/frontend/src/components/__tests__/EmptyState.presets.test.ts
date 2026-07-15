import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { emptyStatePreset } from "../EmptyState";

const CSS = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/EmptyState.module.css";

describe("Plan 140 F3 — EmptyState presets", () => {
  it("variante review con copy exacto", () => {
    const p = emptyStatePreset("review");
    expect(p.title).toBe("Bandeja al día");
    expect(p.message).toContain("No hay ejecuciones que requieran tu revisión");
  });
  it("variante docs con copy exacto y acción", () => {
    const p = emptyStatePreset("docs");
    expect(p.title).toBe("Sin documentación indexada");
    expect(p.actionLabel).toBe("Indexar ahora");
  });
  it("variante no_project con copy exacto", () => {
    const p = emptyStatePreset("no_project");
    expect(p.title).toBe("Ningún proyecto activo");
  });
  it("conserva variantes previas (agents/history)", () => {
    expect(emptyStatePreset("agents").title).toBe("Tu equipo está vacío");
    expect(emptyStatePreset("history").title).toBe("Sin historial todavía");
  });
  it("el CSS ya no tiene el #fff del botón crudo", () => {
    const css = readFileSync(CSS, "utf-8");
    expect(/#fff\b/i.test(css)).toBe(false);
  });
});

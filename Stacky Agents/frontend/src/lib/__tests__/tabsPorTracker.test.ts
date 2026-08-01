// Plan 282 F7 — las pantallas ADO-only dejan de ser callejones sin salida.
import { describe, it, expect } from "vitest";
import { TABS_SOLO_ADO, tabDisponible, motivoNoDisponible } from "../tabsPorTracker";

describe("Plan 282 F7 — tabsPorTracker", () => {
  it("1 — ADO PRIMERO: PM está disponible en un proyecto ADO", () => {
    expect(tabDisponible("pm", "azure_devops")).toBe(true);
  });

  it("2 — PM NO está disponible en GitLab", () => {
    expect(tabDisponible("pm", "gitlab")).toBe(false);
  });

  it("3 — los tabs normales no se rompen", () => {
    expect(tabDisponible("tickets", "gitlab")).toBe(true);
    expect(tabDisponible("devops", "gitlab")).toBe(true);
    expect(tabDisponible("settings", "gitlab")).toBe(true);
  });

  it("4 — sin proyecto falla ABIERTO (los gates que nacen false matan el deep link)", () => {
    expect(tabDisponible("pm", null)).toBe(true);
    expect(tabDisponible("pm", undefined)).toBe(true);
    expect(tabDisponible("pm", "")).toBe(true);
  });

  it("5 — el motivo menciona el tracker real y no está vacío", () => {
    const motivo = motivoNoDisponible("pm", "gitlab");
    expect(motivo).toContain("GitLab");
    expect(motivo).toContain("Azure DevOps");
    expect(motivo.trim().length).toBeGreaterThan(0);
    // Disponible => sin motivo: el tooltip no miente en un proyecto ADO.
    expect(motivoNoDisponible("pm", "azure_devops")).toBe("");
  });

  it("6 — sentinela de contrato: TABS_SOLO_ADO tiene exactamente 3 entradas", () => {
    // Si alguien agrega un tab ADO-only, este test lo obliga a declararlo acá.
    expect(TABS_SOLO_ADO.length).toBe(3);
    expect([...TABS_SOLO_ADO].sort()).toEqual(["pm", "sprint", "userstats"]);
  });

  it("7 — guarda anti-falso-verde: con la lista vacía los casos 1, 3 y 4 pasarían igual", () => {
    // Los tres tabs declarados DEBEN dar false en GitLab; sin esto, un
    // TABS_SOLO_ADO = [] pasaría el 1, el 3 y el 4 sin arreglar nada.
    for (const tab of TABS_SOLO_ADO) {
      expect(tabDisponible(tab, "gitlab")).toBe(false);
      expect(motivoNoDisponible(tab, "gitlab").length).toBeGreaterThan(0);
    }
  });
});

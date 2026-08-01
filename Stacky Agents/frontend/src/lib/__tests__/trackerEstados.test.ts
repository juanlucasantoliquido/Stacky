// Plan 282 F6 — el filtro "Solo abiertos" y los colores dejan de ser ciegos.
import { describe, it, expect } from "vitest";
import {
  esEstadoCerrado, colorDeEstado, sugerenciasDeEstadoCerrado,
} from "../trackerEstados";

describe("Plan 282 F6 — trackerEstados", () => {
  it("1 — ADO PRIMERO: Done cierra en ADO", () => {
    expect(esEstadoCerrado("Done", "azure_devops")).toBe(true);
  });

  it("2 — Active no cierra en ADO", () => {
    expect(esEstadoCerrado("Active", "azure_devops")).toBe(false);
  });

  it("3 — closed cierra en GitLab", () => {
    expect(esEstadoCerrado("closed", "gitlab")).toBe(true);
  });

  it("4 — la comparación es CASE-INSENSITIVE (GitLab devuelve minúsculas)", () => {
    expect(esEstadoCerrado("Closed", "gitlab")).toBe(true);
    expect(esEstadoCerrado("CLOSED", "gitlab")).toBe(true);
  });

  it("5 — opened NO cierra en GitLab", () => {
    expect(esEstadoCerrado("opened", "gitlab")).toBe(false);
  });

  it("6 — un estado ADO no cierra un ticket GitLab", () => {
    expect(esEstadoCerrado("Done", "gitlab")).toBe(false);
    expect(esEstadoCerrado("Resolved", "gitlab")).toBe(false);
  });

  it("7 — null no lanza y no cierra", () => {
    expect(esEstadoCerrado(null, "gitlab")).toBe(false);
    expect(esEstadoCerrado(undefined, null)).toBe(false);
  });

  it("8 — GitLab dejó de caer todo al mismo gris", () => {
    // ESTE es el assert que prueba el arreglo, no la ausencia de error.
    expect(colorDeEstado("opened", "gitlab")).not.toBe(colorDeEstado("closed", "gitlab"));
    // Guarda: el defecto ERA que ambos daban el neutro. Si vuelve, esto lo caza.
    expect(colorDeEstado("opened", "gitlab")).not.toBe("#6b7280");
    expect(colorDeEstado("closed", "gitlab")).not.toBe("#6b7280");
    // ADO congelado: los colores de hoy no cambian.
    expect(colorDeEstado("Done", "azure_devops")).toBe("#22c55e");
    expect(colorDeEstado("Active", "azure_devops")).toBe("#3b82f6");
    expect(colorDeEstado(undefined, "azure_devops")).toBe("#6b7280");
    // La LISTA que consume canResolveWithAgent sigue siendo una lista.
    expect(sugerenciasDeEstadoCerrado("azure_devops")).toContain("Done");
    expect(sugerenciasDeEstadoCerrado("gitlab")).toContain("closed");
  });
});

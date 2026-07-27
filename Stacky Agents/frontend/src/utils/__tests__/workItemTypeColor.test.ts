/**
 * Distintivo visual de INCIDENCIA en el board.
 *
 * El operador reportó que las incidencias no se reconocían de un vistazo: el
 * badge de tipo del grafo se pintaba gris tenue para TODOS los tipos y la
 * vista de árbol directamente no mostraba el tipo. El resaltado se apoya en
 * estos helpers puros (RTL/jsdom no está disponible en este frontend, ver
 * gotcha-rtl-jsdom-structural-gap: el wiring se valida en smoke manual).
 */
import { describe, it, expect } from "vitest";
import {
  INCIDENT_ICON,
  formatWorkItemTypeLabel,
  getWorkItemTypeColor,
  isIncidentWorkItemType,
} from "../workItemTypeColor";

describe("isIncidentWorkItemType", () => {
  it("reconoce los tipos con los que el tracker publica incidencias", () => {
    expect(isIncidentWorkItemType("Issue")).toBe(true);
    expect(isIncidentWorkItemType("Bug")).toBe(true);
  });

  it("es tolerante a mayúsculas y espacios (el valor viene crudo de ADO)", () => {
    expect(isIncidentWorkItemType("  issue ")).toBe(true);
    expect(isIncidentWorkItemType("BUG")).toBe(true);
  });

  it("no marca como incidencia a los demás tipos ni a los nulos", () => {
    for (const t of ["Task", "User Story", "Epic", "Feature", "", null, undefined]) {
      expect(isIncidentWorkItemType(t)).toBe(false);
    }
  });
});

describe("formatWorkItemTypeLabel", () => {
  it("prefija la incidencia con ícono: el distintivo NO depende solo del color", () => {
    expect(formatWorkItemTypeLabel("Issue")).toBe(`${INCIDENT_ICON} Issue`);
    expect(formatWorkItemTypeLabel("Bug")).toBe(`${INCIDENT_ICON} Bug`);
  });

  it("deja intactos los tipos que no son incidencia", () => {
    expect(formatWorkItemTypeLabel("Task")).toBe("Task");
    expect(formatWorkItemTypeLabel("Epic")).toBe("Epic");
  });

  it("devuelve vacío sin tipo (no renderiza un badge fantasma)", () => {
    expect(formatWorkItemTypeLabel(null)).toBe("");
    expect(formatWorkItemTypeLabel("   ")).toBe("");
  });
});

describe("getWorkItemTypeColor", () => {
  it("la incidencia no cae en el gris neutro por defecto", () => {
    const neutral = getWorkItemTypeColor("TipoQueNoExiste");
    expect(getWorkItemTypeColor("Issue")).not.toBe(neutral);
    expect(getWorkItemTypeColor("Bug")).not.toBe(neutral);
  });

  it("la incidencia se distingue de los tipos de trabajo normal", () => {
    const issue = getWorkItemTypeColor("Issue");
    expect(issue).not.toBe(getWorkItemTypeColor("Task"));
    expect(issue).not.toBe(getWorkItemTypeColor("Epic"));
    expect(issue).not.toBe(getWorkItemTypeColor("Feature"));
  });
});

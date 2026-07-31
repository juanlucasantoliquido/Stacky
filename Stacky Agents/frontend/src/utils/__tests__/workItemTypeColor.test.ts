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

  it("deja intactos los tipos que no son incidencia y no tienen rótulo propio", () => {
    expect(formatWorkItemTypeLabel("Task")).toBe("Task");
    expect(formatWorkItemTypeLabel("Feature")).toBe("Feature");
  });

  // Plan 277 — el token guardado es ASCII sin acento (lo exige el contrato de
  // etiquetas); el acento vive solo en el rótulo que ve el operador.
  it("traduce los tipos del contrato a su rótulo acentuado", () => {
    expect(formatWorkItemTypeLabel("Epic")).toBe("Épica");
    expect(formatWorkItemTypeLabel("funcional")).toBe("Análisis Funcional");
    expect(formatWorkItemTypeLabel("Tecnico")).toBe("Análisis Técnico");
    expect(formatWorkItemTypeLabel("implementacion")).toBe("Implementación");
  });

  it("conserva el prefijo de incidencia, que existe por a11y", () => {
    expect(formatWorkItemTypeLabel("Issue")).toBe(`${INCIDENT_ICON} Issue`);
    expect(formatWorkItemTypeLabel("Bug")).toBe(`${INCIDENT_ICON} Bug`);
  });

  it("un tipo sin rótulo propio pasa crudo y sin tocar", () => {
    // Guarda de la búsqueda nueva: el `?? raw` tiene que dejar pasar cualquier
    // tipo que el tracker publique y que no esté en el mapa.
    expect(formatWorkItemTypeLabel("User Story")).toBe("User Story");
    expect(formatWorkItemTypeLabel("  Historia de Usuario  ")).toBe("Historia de Usuario");
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

  // Plan 277 — las 3 fases del contrato de jerarquía tienen color propio: sin
  // esto los tres badges salen del mismo gris y el grafo no se lee de un vistazo.
  it("las tres fases del contrato no caen en el gris por defecto", () => {
    const neutral = getWorkItemTypeColor("TipoQueNoExiste");
    for (const t of ["funcional", "Tecnico", "IMPLEMENTACION"]) {
      expect(getWorkItemTypeColor(t)).not.toBe(neutral);
    }
    // Y son distinguibles entre sí y de la épica de la que cuelgan.
    const colores = ["funcional", "tecnico", "epic"].map(getWorkItemTypeColor);
    expect(new Set(colores).size).toBe(3);
  });
});

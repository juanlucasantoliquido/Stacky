/**
 * Plan 270 F5 + F7 — Tests PUROS de la deteccion de divergencia.
 * Sin RTL, sin jsdom: el repo no los tiene instalados.
 * 19 casos: 16 de F5 (divergencia) + 3 de F7 (texto del dry-run).
 */
import { describe, expect, it } from "vitest";

import type { IncidentInboxItem, IncidentInboxStatus } from "./incidentInboxModel";
import {
  countDiverged,
  describeCloseDestination,
  divergenceSummary,
  filterDiverged,
  formatDivergenceCount,
  isDiverged,
  resolveDivergenceBadgeEnabled,
  resolveDivergenceCount,
} from "./incidentDivergence";

function item(over: Partial<IncidentInboxItem> = {}): IncidentInboxItem {
  return {
    id: 1,
    ado_id: 100,
    title: "incidencia de prueba",
    is_open: true,
    ...over,
  };
}

const status: IncidentInboxStatus = {
  ok: true,
  enabled: true,
  incident_types: ["issue", "bug"],
  incident_types_source: "default",
  closed_states: ["Done"],
  closed_states_source: "default",
};

/** 3 divergentes de 7. */
const visible: IncidentInboxItem[] = [
  item({ ado_id: 1, stacky_status: "completed", is_open: true }),
  item({ ado_id: 2, stacky_status: "completed", is_open: true }),
  item({ ado_id: 3, stacky_status: "completed", is_open: true }),
  item({ ado_id: 4, stacky_status: "completed", is_open: false }),
  item({ ado_id: 5, stacky_status: "running", is_open: true }),
  item({ ado_id: 6, stacky_status: "error", is_open: true }),
  item({ ado_id: 7, is_open: true }),
];

describe("plan 270 F5 — divergencia", () => {
  it("1. completed + abierta => divergente", () => {
    expect(isDiverged(item({ stacky_status: "completed", is_open: true }))).toBe(true);
  });

  it("2. completed + cerrada => NO divergente", () => {
    expect(isDiverged(item({ stacky_status: "completed", is_open: false }))).toBe(false);
  });

  it("3. running + abierta => NO divergente (esta trabajando)", () => {
    expect(isDiverged(item({ stacky_status: "running", is_open: true }))).toBe(false);
  });

  it("4. error + abierta => NO divergente (fallo, se ve por otro lado)", () => {
    expect(isDiverged(item({ stacky_status: "error", is_open: true }))).toBe(false);
  });

  it("5. sin stacky_status (backend viejo) => NO divergente, nunca marca de mas", () => {
    expect(isDiverged(item({ is_open: true }))).toBe(false);
  });

  it("6. cuenta y resume una lista con 3 divergentes de 7", () => {
    expect(countDiverged(visible)).toBe(3);
    expect(divergenceSummary(visible)).toBe("3 sin sincronizar");
  });

  it("7. lista sin divergentes => cadena vacia (no se pinta un chip con cero)", () => {
    expect(divergenceSummary([item({ stacky_status: "completed", is_open: false })])).toBe("");
    expect(divergenceSummary([])).toBe("");
  });

  it("8. una sola divergente usa el singular", () => {
    expect(divergenceSummary([item({ stacky_status: "completed", is_open: true })])).toBe(
      "1 sin sincronizar",
    );
  });

  it("9. filterDiverged filtra o devuelve la lista intacta", () => {
    const soloDiv = filterDiverged(visible, true);
    expect(soloDiv).toHaveLength(3);
    expect(soloDiv.every(isDiverged)).toBe(true);
    const todas = filterDiverged(visible, false);
    expect(todas).toHaveLength(7);
    expect(todas[0]).toBe(visible[0]);
  });

  it("10. el gate del badge es estricto: undefined y null => false", () => {
    expect(resolveDivergenceBadgeEnabled(undefined)).toBe(false);
    expect(resolveDivergenceBadgeEnabled(null)).toBe(false);
  });

  it("11. el gate del badge exige true literal, nunca fail-open", () => {
    expect(resolveDivergenceBadgeEnabled({ ...status, divergence_badge_enabled: true })).toBe(true);
    expect(resolveDivergenceBadgeEnabled(status)).toBe(false);
    expect(resolveDivergenceBadgeEnabled({ ...status, divergence_badge_enabled: false })).toBe(false);
  });

  it("12. el numero del chip no se calcula sobre la lista ya filtrada", () => {
    const texto = divergenceSummary(visible);
    const filtradas = filterDiverged(visible, true);
    expect(texto).toBe("3 sin sincronizar");
    expect(filtradas).toHaveLength(3);
    // Y el texto sigue siendo el mismo tras filtrar: no se congela en si mismo.
    expect(divergenceSummary(visible)).toBe(texto);
  });

  it("13. formatDivergenceCount: 0/negativo/NaN => vacio", () => {
    expect(formatDivergenceCount(0)).toBe("");
    expect(formatDivergenceCount(1)).toBe("1 sin sincronizar");
    expect(formatDivergenceCount(7)).toBe("7 sin sincronizar");
    expect(formatDivergenceCount(-2)).toBe("");
    expect(formatDivergenceCount(NaN)).toBe("");
  });

  it("14. el conteo del SERVIDOR manda, incluido un 0 explicito", () => {
    expect(resolveDivergenceCount(9, visible)).toBe(9);
    expect(resolveDivergenceCount(undefined, visible)).toBe(3);
    expect(resolveDivergenceCount(null, visible)).toBe(3);
    expect(resolveDivergenceCount(0, visible)).toBe(0);
  });

  it("15. la key del backend LLEGA al texto del chip", () => {
    const dto = { diverged_count: 4 };
    expect(formatDivergenceCount(resolveDivergenceCount(dto.diverged_count, visible))).toBe(
      "4 sin sincronizar",
    );
  });

  it("16. [E2] un NaN/Infinity del servidor NO puede borrar el chip", () => {
    // El UNICO caso que mata la implementacion prohibida `serverCount ?? local`:
    // con `??`, (a) devolveria NaN y (c) devolveria "" => el chip desaparece.
    expect(resolveDivergenceCount(NaN, visible)).toBe(3);
    expect(resolveDivergenceCount(Infinity, visible)).toBe(3);
    expect(formatDivergenceCount(resolveDivergenceCount(NaN, visible))).toBe("3 sin sincronizar");
  });
});

describe("plan 270 F7 — texto del destino en el dry-run", () => {
  it("17. destino resuelto en Azure DevOps", () => {
    expect(
      describeCloseDestination({
        resolved: true,
        tracker_type: "azure_devops",
        native_state: "Done",
        closes: true,
      }),
    ).toBe('Se escribe en Azure DevOps como "Done" — queda cerrada.');
  });

  it("18. destino resuelto en GitLab que cierra", () => {
    expect(
      describeCloseDestination({
        resolved: true,
        tracker_type: "gitlab",
        native_state: "accepted",
        closes: true,
      }),
    ).toBe('Se escribe en GitLab como "accepted" — queda cerrada.');
  });

  it("19. destino NO resuelto: muestra la causa y el workaround accionable", () => {
    const texto = describeCloseDestination({
      resolved: false,
      tracker_type: "gitlab",
      reason: "el proveedor GitLab no esta disponible",
      workaround: "activa la integracion en Configuracion > Arnes.",
    });
    expect(texto).toContain("No se puede cerrar");
    expect(texto).toContain("el proveedor GitLab no esta disponible");
    expect(texto).toContain("activa la integracion en Configuracion > Arnes.");
    // Sin destino => sin texto (no se inventa nada).
    expect(describeCloseDestination(null)).toBe("");
    expect(describeCloseDestination(undefined)).toBe("");
    // Resuelto pero que NO cierra: se dice explicito.
    expect(
      describeCloseDestination({
        resolved: true,
        tracker_type: "azure_devops",
        native_state: "Active",
        closes: false,
      }),
    ).toContain("NO queda cerrada");
  });
});

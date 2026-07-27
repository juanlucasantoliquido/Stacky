import { describe, it, expect } from "vitest";
import {
  BULK_FINISH_REASON,
  DEFAULT_FINISH_STATE,
  canFinishIncident,
  canResolveIncident,
  normalizeFinishState,
  partitionSelection,
  resolveInboxActionsEnabled,
  skippedNotice,
} from "./incidentInboxActionsModel";
import type { IncidentInboxItem, IncidentInboxStatus } from "./incidentInboxModel";

const CLOSED = ["Done", "Closed", "Resolved", "Removed", "Completed"];

function item(over: Partial<IncidentInboxItem> = {}): IncidentInboxItem {
  return {
    id: 1,
    ado_id: 100,
    title: "Una incidencia",
    work_item_type: "Issue",
    ado_state: "Active",
    is_open: true,
    ...over,
  };
}

function status(over: Partial<IncidentInboxStatus> = {}): IncidentInboxStatus {
  return {
    ok: true,
    enabled: true,
    incident_types: ["issue", "bug"],
    incident_types_source: "default",
    closed_states: CLOSED,
    closed_states_source: "default",
    ...over,
  };
}

describe("resolveInboxActionsEnabled", () => {
  it("true solo con actions_enabled === true", () => {
    expect(resolveInboxActionsEnabled(status({ actions_enabled: true }))).toBe(true);
  });

  it("false con la flag apagada", () => {
    expect(resolveInboxActionsEnabled(status({ actions_enabled: false }))).toBe(false);
  });

  it("false con backend viejo que no manda la key (solo lectura del 238)", () => {
    expect(resolveInboxActionsEnabled(status())).toBe(false);
  });

  it("false con status null/undefined (todavia cargando)", () => {
    expect(resolveInboxActionsEnabled(null)).toBe(false);
    expect(resolveInboxActionsEnabled(undefined)).toBe(false);
  });
});

describe("normalizeFinishState", () => {
  it("cae a Done con vacio, espacios, null o undefined", () => {
    expect(normalizeFinishState("")).toBe(DEFAULT_FINISH_STATE);
    expect(normalizeFinishState("   ")).toBe(DEFAULT_FINISH_STATE);
    expect(normalizeFinishState(null)).toBe(DEFAULT_FINISH_STATE);
    expect(normalizeFinishState(undefined)).toBe(DEFAULT_FINISH_STATE);
  });

  it("respeta y recorta lo que escriba el operador", () => {
    expect(normalizeFinishState("  Closed ")).toBe("Closed");
  });
});

describe("canFinishIncident", () => {
  it("permite cerrar una abierta con las acciones ON", () => {
    expect(canFinishIncident({ item: item(), actionsEnabled: true })).toBe(true);
  });

  it("no ofrece cerrar una ya cerrada", () => {
    expect(
      canFinishIncident({ item: item({ is_open: false, ado_state: "Done" }), actionsEnabled: true }),
    ).toBe(false);
  });

  it("no ofrece nada con las acciones OFF", () => {
    expect(canFinishIncident({ item: item(), actionsEnabled: false })).toBe(false);
  });
});

describe("canResolveIncident", () => {
  const base = { actionsEnabled: true, devResolverEnabled: true, closedStates: CLOSED };

  it("permite resolver una Issue abierta y sin agente corriendo", () => {
    expect(canResolveIncident({ item: item(), ...base })).toBe(true);
  });

  it("permite resolver un Bug (mismo criterio que el tablero)", () => {
    expect(canResolveIncident({ item: item({ work_item_type: "Bug" }), ...base })).toBe(true);
  });

  it("no resuelve una Task", () => {
    expect(canResolveIncident({ item: item({ work_item_type: "Task" }), ...base })).toBe(false);
  });

  it("no resuelve una cerrada", () => {
    expect(canResolveIncident({ item: item({ ado_state: "Done" }), ...base })).toBe(false);
  });

  it("no resuelve si ya hay un agente corriendo", () => {
    expect(canResolveIncident({ item: item({ stacky_status: "running" }), ...base })).toBe(false);
  });

  it("no resuelve con el Dev Resolutor apagado", () => {
    expect(canResolveIncident({ item: item(), ...base, devResolverEnabled: false })).toBe(false);
  });

  it("no resuelve con las acciones de la bandeja apagadas", () => {
    expect(canResolveIncident({ item: item(), ...base, actionsEnabled: false })).toBe(false);
  });
});

describe("partitionSelection", () => {
  const items = [
    item({ id: 1, is_open: true }),
    item({ id: 2, is_open: false, ado_state: "Done" }),
    item({ id: 3, is_open: true }),
  ];
  const puedeCerrar = (i: IncidentInboxItem) => canFinishIncident({ item: i, actionsEnabled: true });

  it("separa elegibles de salteados", () => {
    expect(partitionSelection(items, [1, 2, 3], puedeCerrar)).toEqual({
      eligible: [1, 3],
      skipped: [2],
    });
  });

  it("conserva el orden de la seleccion, no el de la lista", () => {
    expect(partitionSelection(items, [3, 1], puedeCerrar).eligible).toEqual([3, 1]);
  });

  it("deduplica ids repetidos", () => {
    expect(partitionSelection(items, [1, 1, 3], puedeCerrar).eligible).toEqual([1, 3]);
  });

  it("un id desconocido se saltea, jamas se cuela como elegible", () => {
    const r = partitionSelection(items, [1, 999], puedeCerrar);
    expect(r.eligible).toEqual([1]);
    expect(r.skipped).toEqual([999]);
  });

  it("seleccion vacia devuelve dos listas vacias", () => {
    expect(partitionSelection(items, [], puedeCerrar)).toEqual({ eligible: [], skipped: [] });
  });
});

describe("skippedNotice", () => {
  it("null cuando no se saltea nada", () => {
    expect(skippedNotice([])).toBeNull();
  });

  it("singular con una sola", () => {
    expect(skippedNotice([7])).toContain("1 seleccionada");
  });

  it("plural con varias", () => {
    expect(skippedNotice([7, 8, 9])).toContain("3 seleccionadas");
  });
});

describe("constantes del lote", () => {
  it("el motivo del cierre en lote cumple el minimo de 5 chars del backend", () => {
    expect(BULK_FINISH_REASON.trim().length).toBeGreaterThanOrEqual(5);
  });
});

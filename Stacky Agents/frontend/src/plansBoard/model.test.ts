import { describe, expect, it } from "vitest";
import {
  ESTADO_CHIP,
  buildCopyPayload,
  estadoChip,
  filterPlans,
  sinSupervisar,
  type BoardFilters,
  type PlanCardDto,
} from "./model";

function card(overrides: Partial<PlanCardDto> = {}): PlanCardDto {
  return {
    number: 128,
    number_str: "128",
    slug: "TABLERO_EVOLUCION_PLANES",
    filename: "128_PLAN_TABLERO_EVOLUCION_PLANES.md",
    path_rel: "Stacky Agents/docs/128_PLAN_TABLERO_EVOLUCION_PLANES.md",
    title: "Plan 128 — Tablero de Evolución de Planes",
    estado: "PROPUESTO",
    estado_raw: "PROPUESTO (v1)",
    estado_efectivo: "PROPUESTO",
    veredicto: null,
    version: "1",
    fecha: null,
    duplicate: false,
    ledger: null,
    unpushed: null,
    suggested_action: {
      kind: "criticar",
      label: "Criticar plan",
      command: "/criticar-y-mejorar-plan 128",
      natural_language: "Pedile al agente criticar y mejorar el plan 128.",
    },
    ...overrides,
  };
}

const baseFilters: BoardFilters = {
  texto: "",
  estado: "TODOS",
  soloPendientesPush: false,
  soloSinSupervisar: false,
};

describe("estadoChip", () => {
  it("mapea APROBADO al chip verde", () => {
    const c = card({ estado_efectivo: "APROBADO" });
    expect(estadoChip(c)).toEqual(ESTADO_CHIP.APROBADO);
    expect(estadoChip(c).color).toBe("#22c55e");
  });

  it("cae a SIN_ESTADO ante una clave desconocida", () => {
    const c = card({ estado_efectivo: "ALGO_RARO" as unknown as PlanCardDto["estado_efectivo"] });
    expect(estadoChip(c)).toEqual(ESTADO_CHIP.SIN_ESTADO);
  });
});

describe("sinSupervisar", () => {
  it("true para IMPLEMENTADO e IMPLEMENTADO_PARCIAL, false para APROBADO/PROPUESTO", () => {
    expect(sinSupervisar(card({ estado_efectivo: "IMPLEMENTADO" }))).toBe(true);
    expect(sinSupervisar(card({ estado_efectivo: "IMPLEMENTADO_PARCIAL" }))).toBe(true);
    expect(sinSupervisar(card({ estado_efectivo: "APROBADO" }))).toBe(false);
    expect(sinSupervisar(card({ estado_efectivo: "PROPUESTO" }))).toBe(false);
  });
});

describe("filterPlans", () => {
  const plans = [
    card({ number: 128, number_str: "128", title: "Tablero de Evolución", slug: "TABLERO", estado_efectivo: "PROPUESTO", unpushed: true }),
    card({ number: 90, number_str: "90", title: "Agente DevOps", slug: "DEVOPS_AGENT", estado_efectivo: "APROBADO", unpushed: false }),
    card({ number: 117, number_str: "117", title: "Insights locales", slug: "INSIGHTS", estado_efectivo: "IMPLEMENTADO", unpushed: null }),
  ];

  it("filtra por texto case-insensitive sobre número/título/slug", () => {
    expect(filterPlans(plans, { ...baseFilters, texto: "tablero" }).map((c) => c.number)).toEqual([128]);
    expect(filterPlans(plans, { ...baseFilters, texto: "128" }).map((c) => c.number)).toEqual([128]);
    expect(filterPlans(plans, { ...baseFilters, texto: "DEVOPS_AGENT" }).map((c) => c.number)).toEqual([90]);
  });

  it("filtra por estado", () => {
    expect(filterPlans(plans, { ...baseFilters, estado: "APROBADO" }).map((c) => c.number)).toEqual([90]);
  });

  it("filtra por soloPendientesPush", () => {
    expect(filterPlans(plans, { ...baseFilters, soloPendientesPush: true }).map((c) => c.number)).toEqual([128]);
  });

  it("AND de filtros combinados", () => {
    const result = filterPlans(plans, { ...baseFilters, texto: "insights", soloSinSupervisar: true });
    expect(result.map((c) => c.number)).toEqual([117]);
    const empty = filterPlans(plans, { ...baseFilters, texto: "insights", soloPendientesPush: true });
    expect(empty).toEqual([]);
  });

  it("no muta el array de entrada", () => {
    const before = JSON.parse(JSON.stringify(plans));
    filterPlans(plans, { ...baseFilters, texto: "x" });
    expect(plans).toEqual(before);
  });
});

describe("buildCopyPayload", () => {
  it("usa command cuando está presente", () => {
    const a = { kind: "criticar", label: "x", command: "/criticar-y-mejorar-plan 128", natural_language: "nl" };
    expect(buildCopyPayload(a)).toBe("/criticar-y-mejorar-plan 128");
  });

  it("cae a natural_language cuando command es null", () => {
    const a = { kind: "ok", label: "x", command: null, natural_language: "Plan 90 al día." };
    expect(buildCopyPayload(a)).toBe("Plan 90 al día.");
  });
});

// Plan 237 F5 — tests del modelo puro del triage de planes.
import { describe, it, expect } from "vitest";
import {
  BUCKET_ORDER,
  BUCKET_META,
  BUCKETS_ABIERTOS_POR_DEFECTO,
  bucketRank,
  groupByBucket,
  filterByText,
  censusSummary,
  numberingAlert,
  type PlanTriageCard,
  type PlansTriageDto,
} from "./plansTriageModel";

function mk(over: Partial<PlanTriageCard> = {}): PlanTriageCard {
  return {
    number: 1,
    number_str: "01",
    title: "Plan uno",
    slug: "PLAN_UNO",
    filename: "01_PLAN_UNO.md",
    estado: "PROPUESTO",
    estado_efectivo: "PROPUESTO",
    triage_bucket: "SIN_CRITICAR",
    version: null,
    fecha: null,
    duplicate: false,
    unpushed: null,
    ledger: null,
    suggested_action: { kind: "criticar", label: "Criticar plan", command: "/criticar-y-mejorar-plan 01", natural_language: "frase" },
    ...over,
  };
}

const CENSO_CERO: PlansTriageDto["census"] = {
  files_seen: 3,
  plans_parsed: 3,
  skipped_not_a_plan: 0,
  skipped_oversize: 0,
  skipped_unreadable: 0,
  skipped_over_cap: 0,
  skipped_subdirs: 0,
  subdir_examples: [],
};

describe("plansTriageModel", () => {
  it("BUCKET_ORDER es el contrato: sin implementar primero, completado último", () => {
    expect(BUCKET_ORDER).toEqual(["SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR", "COMPLETADO"]);
  });

  it("COMPLETADO es el único bucket cerrado por defecto", () => {
    expect(BUCKETS_ABIERTOS_POR_DEFECTO).not.toContain("COMPLETADO");
    expect(BUCKETS_ABIERTOS_POR_DEFECTO).toHaveLength(4);
  });

  it("BUCKET_META cubre todos los buckets y ninguno trae color literal", () => {
    for (const b of BUCKET_ORDER) {
      expect(BUCKET_META[b].label.length).toBeGreaterThan(0);
      expect(BUCKET_META[b].hint.length).toBeGreaterThan(0);
      expect(BUCKET_META[b].tone).not.toMatch(/#[0-9a-fA-F]{3}/);
    }
  });

  it("groupByBucket devuelve los 5 grupos en orden, aun vacíos", () => {
    const grupos = groupByBucket([]);
    expect(grupos).toHaveLength(5);
    expect(grupos.map((g) => g.bucket)).toEqual(BUCKET_ORDER);
    expect(grupos.every((g) => g.cards.length === 0)).toBe(true);
  });

  it("groupByBucket ordena por número descendente dentro del grupo", () => {
    const plans = [
      mk({ number: 10, triage_bucket: "SIN_IMPLEMENTAR" }),
      mk({ number: 90, triage_bucket: "SIN_IMPLEMENTAR" }),
      mk({ number: 50, triage_bucket: "SIN_IMPLEMENTAR" }),
    ];
    const grupo = groupByBucket(plans)[0];
    expect(grupo.cards.map((c) => c.number)).toEqual([90, 50, 10]);
  });

  it("bucketRank manda lo desconocido al final", () => {
    expect(bucketRank("MARCIANO")).toBe(BUCKET_ORDER.length);
    expect(bucketRank("SIN_IMPLEMENTAR")).toBe(0);
    expect(bucketRank("COMPLETADO")).toBe(4);
  });

  it("filterByText matchea número, título y slug, y respeta el vacío", () => {
    const plans = [
      mk({ number: 216, number_str: "216", title: "Estados del cliente", slug: "ESTADOS" }),
      mk({ number: 218, number_str: "218", title: "Paridad total", slug: "PARIDAD_GITLAB" }),
    ];
    expect(filterByText(plans, "216").map((p) => p.number)).toEqual([216]);
    expect(filterByText(plans, "paridad").map((p) => p.number)).toEqual([218]);
    expect(filterByText(plans, "GITLAB").map((p) => p.number)).toEqual([218]);
    expect(filterByText(plans, "")).toHaveLength(2);
    expect(filterByText(plans, "   ")).toHaveLength(2);
  });

  it("censusSummary devuelve null cuando no se excluyó nada", () => {
    expect(censusSummary(CENSO_CERO)).toBeNull();
  });

  it("censusSummary nombra cada motivo de exclusión", () => {
    const s = censusSummary({
      ...CENSO_CERO,
      skipped_subdirs: 3,
      skipped_oversize: 1,
      skipped_unreadable: 2,
      skipped_over_cap: 4,
    });
    expect(s).toContain("3 archivados en subcarpetas");
    expect(s).toContain("1 demasiado grandes");
    expect(s).toContain("2 ilegibles");
    expect(s).toContain("4 más allá del tope de lectura");
  });

  it("numberingAlert es null sin duplicados y nombra los archivos con duplicados", () => {
    expect(numberingAlert(undefined)).toBeNull();
    expect(numberingAlert({ max_number: 238, next_free_number: 239, next_free_number_raw: 239,
                            reserved_count: 19, duplicates: [] })).toBeNull();
    const s = numberingAlert({ max_number: 238, next_free_number: 239, next_free_number_raw: 239,
      reserved_count: 19, duplicates: [{ number: 237, filenames: ["237_PLAN_A.md", "237_PLAN_B.md"] }] });
    expect(s).toContain("237");
    expect(s).toContain("237_PLAN_B.md");
  });
});

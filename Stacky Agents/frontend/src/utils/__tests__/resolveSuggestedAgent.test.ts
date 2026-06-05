/**
 * Tests unitarios — resolveSuggestedAgent.ts (B5)
 *
 * Capa: unit. Sin dependencias de DOM.
 *
 * Para ejecutar:
 *   npx vitest run src/utils/__tests__/resolveSuggestedAgent.test.ts
 */
import { describe, it, expect } from "vitest";
import { resolveSuggestedAgent } from "../resolveSuggestedAgent";

const flow = (entries: Array<[string, string]>) => new Map(entries);

describe("resolveSuggestedAgent", () => {
  it("(1) usa FlowConfig por estado cuando hay regla (case-insensitive)", () => {
    const map = flow([["active", "developer"]]);
    expect(
      resolveSuggestedAgent({ workItemType: "Task", adoState: "Active", flowConfigMap: map })
    ).toBe("developer");
    // El map se consulta en minúsculas; el estado entra con casing arbitrario.
    expect(
      resolveSuggestedAgent({ workItemType: "Task", adoState: "ACTIVE", flowConfigMap: map })
    ).toBe("developer");
  });

  it("(2) cae a pipelineNext cuando FlowConfig no tiene regla para el estado", () => {
    const map = flow([["new", "business"]]); // no cubre "Committed"
    expect(
      resolveSuggestedAgent({
        workItemType: "Feature",
        adoState: "Committed",
        flowConfigMap: map,
        pipelineNext: "technical",
      })
    ).toBe("technical");
  });

  it("(3) fallback por tipo cuando no hay FlowConfig ni pipeline (el bug B5)", () => {
    const map = flow([]); // estado no mapeado
    // Antes esto devolvía null → botón deshabilitado. Ahora sugiere por tipo.
    expect(
      resolveSuggestedAgent({ workItemType: "Feature", adoState: "To Do", flowConfigMap: map })
    ).toBe("technical");
    expect(
      resolveSuggestedAgent({ workItemType: "Task", adoState: "To Do", flowConfigMap: map })
    ).toBe("developer");
    expect(
      resolveSuggestedAgent({ workItemType: "Bug", adoState: "To Do", flowConfigMap: map })
    ).toBe("developer");
  });

  it("suprime 'business' en Tasks y cae al siguiente candidato (no null)", () => {
    const map = flow([["new", "business"]]);
    // Un Task "New" mapeado a business: NO debe quedar sin sugerencia.
    // FlowConfig→business (suprimido) → pipelineNext ausente → fallback por tipo.
    expect(
      resolveSuggestedAgent({ workItemType: "Task", adoState: "New", flowConfigMap: map })
    ).toBe("developer");
  });

  it("suprime 'business' del pipeline en Épicas y cae al fallback por tipo", () => {
    const map = flow([]);
    expect(
      resolveSuggestedAgent({
        workItemType: "Epic",
        adoState: "New",
        flowConfigMap: map,
        pipelineNext: "business",
      })
    ).toBe("functional");
  });

  it("permite 'business' para tipos que no son Task/Epic (ej. Feature)", () => {
    const map = flow([["new", "business"]]);
    expect(
      resolveSuggestedAgent({ workItemType: "Feature", adoState: "New", flowConfigMap: map })
    ).toBe("business");
  });

  it("devuelve null cuando no hay ninguna señal ni fallback para el tipo", () => {
    const map = flow([]);
    expect(
      resolveSuggestedAgent({ workItemType: "Impediment", adoState: "Open", flowConfigMap: map })
    ).toBeNull();
  });
});

/**
 * Plan 215 F7 — smoke de módulo de la sección "Publicar Soluciones".
 *
 * NOTA: @testing-library/react y jsdom NO están instalados en este repo, así que
 * este test verifica lo único verificable sin DOM: que el módulo importa (sin
 * ciclos ni imports rotos) y exporta el componente. El gate real es
 * `npx tsc --noEmit` + el smoke manual de la sección.
 */
import { describe, it, expect } from "vitest";

describe("SolutionPublisherSection (plan 215 F7)", () => {
  it("exporta SolutionPublisherSection", async () => {
    const mod = await import("../SolutionPublisherSection");
    expect(mod.SolutionPublisherSection).toBeDefined();
  });

  it("el modelo puro que consume la sección exporta sus helpers", async () => {
    const mod = await import("../solutionPublisherModel");
    expect(typeof mod.canPublish).toBe("function");
    expect(typeof mod.publishStatusLabel).toBe("function");
    expect(typeof mod.commandPreview).toBe("function");
    expect(typeof mod.planReasonLabel).toBe("function");
    expect(typeof mod.parseSolutionPathsFromText).toBe("function");
    expect(typeof mod.needsAttention).toBe("function");
  });

  it("el objeto de endpoints del publicador apunta al blueprint real", async () => {
    const { DevOpsSolutionPublisher } = await import("../../../api/endpoints");
    expect(DevOpsSolutionPublisher.artifactDownloadUrl("r1")).toBe(
      "/api/devops/solution-publisher/runs/r1/artifact/download",
    );
  });
});

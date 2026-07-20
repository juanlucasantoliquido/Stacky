// Plan 169 F5 — tests puros del modelo Optimizador (vitest node env, sin RTL/jsdom).
import { describe, it, expect } from "vitest";
import {
  type ArchiveEntryDto,
  RUN_POLL_MS,
  RUN_POLL_MAX,
  runStatusTone,
  runStatusLabel,
  verdictTone,
  verdictLabel,
  generatorLabel,
  isTerminal,
  lineageRows,
  improvementDisplay,
} from "./optimizerModel";

function entry(over: Partial<ArchiveEntryDto>): ArchiveEntryDto {
  return {
    id: "x", run_id: "opt-1", parent_id: null, kind: "variant", verdict: "dominated",
    invalid_reason: null, fitness: null, cost_proxy: 1, mutation_lesson: null,
    generator_model: null, created_at: "2026-07-18T00:00:00Z", ...over,
  };
}

describe("optimizerModel", () => {
  it("runStatusTone/runStatusLabel los 6 estados exactos", () => {
    expect(runStatusTone("running")).toBe("info");
    expect(runStatusTone("completed")).toBe("success");
    expect(runStatusTone("no_improvement")).toBe("neutral");
    expect(runStatusTone("stopped_budget")).toBe("warning");
    expect(runStatusTone("cancelled")).toBe("neutral");
    expect(runStatusTone("error")).toBe("danger");
    expect(runStatusLabel("running")).toBe("Corriendo");
    expect(runStatusLabel("completed")).toBe("Propuesta emitida");
    expect(runStatusLabel("no_improvement")).toBe("Sin mejora suficiente");
    expect(runStatusLabel("stopped_budget")).toBe("Presupuesto agotado");
    expect(runStatusLabel("cancelled")).toBe("Cancelada");
    expect(runStatusLabel("error")).toBe("Error");
  });

  it("verdictTone/verdictLabel los 5 verdicts", () => {
    expect(verdictTone("winner")).toBe("success");
    expect(verdictTone("pareto")).toBe("info");
    expect(verdictTone("base")).toBe("neutral");
    expect(verdictTone("dominated")).toBe("neutral");
    expect(verdictTone("invalid")).toBe("danger");
    expect(verdictLabel("base")).toBe("Base");
    expect(verdictLabel("winner")).toBe("Ganadora");
    expect(verdictLabel("pareto")).toBe("Frente Pareto");
    expect(verdictLabel("dominated")).toBe("Dominada");
    expect(verdictLabel("invalid")).toBe("Inválida");
  });

  it("generatorLabel local / runtime / desconocido", () => {
    expect(generatorLabel({ mode: "local", runtime: null })).toBe("Modelo local");
    expect(generatorLabel({ mode: "runtime", runtime: "codex_cli" })).toBe("Runtime: codex_cli");
    expect(generatorLabel({ mode: "otro", runtime: null })).toBe("otro");
  });

  it("isTerminal running false, los otros 5 true", () => {
    expect(isTerminal("running")).toBe(false);
    for (const s of ["completed", "no_improvement", "stopped_budget", "cancelled", "error"] as const) {
      expect(isTerminal(s)).toBe(true);
    }
  });

  it("lineageRows: 1 base + 2 hijas + 1 huérfana → orden y depths exactos", () => {
    const base = entry({ id: "b1", kind: "base", verdict: "base", created_at: "2026-07-18T00:00:00Z" });
    const c1 = entry({ id: "c1", parent_id: "b1", created_at: "2026-07-18T00:00:01Z" });
    const c2 = entry({ id: "c2", parent_id: "b1", created_at: "2026-07-18T00:00:02Z" });
    const orphan = entry({ id: "o1", parent_id: "b-inexistente", created_at: "2026-07-18T00:00:03Z" });
    const rows = lineageRows([c2, orphan, base, c1]);
    expect(rows.map((r) => r.entry.id)).toEqual(["b1", "c1", "c2", "o1"]);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 1, 0]);
  });

  it("lineageRows no muta el input", () => {
    const input = [
      entry({ id: "b1", kind: "base", verdict: "base" }),
      entry({ id: "c1", parent_id: "b1" }),
    ];
    const snapshot = JSON.parse(JSON.stringify(input));
    lineageRows(input);
    expect(input).toEqual(snapshot);
  });

  it("improvementDisplay (0.6,0.7) y null", () => {
    expect(improvementDisplay(0.6, 0.7)).toBe("0.60 → 0.70");
    expect(improvementDisplay(null, 0.7)).toBe("—");
  });

  it("RUN_POLL_MS y RUN_POLL_MAX congelados", () => {
    expect(RUN_POLL_MS).toBe(2000);
    expect(RUN_POLL_MAX).toBe(900);
  });
});

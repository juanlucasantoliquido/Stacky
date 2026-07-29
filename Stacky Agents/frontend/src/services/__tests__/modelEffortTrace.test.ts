import { describe, it, expect } from "vitest";
import { formatModelEffortTrace } from "../modelEffortTrace";

describe("Plan 264 F6 — formatModelEffortTrace (función pura, sin DOM)", () => {
  it("1 — undefined/null: devuelve null, no lanza", () => {
    expect(formatModelEffortTrace(undefined)).toBeNull();
    expect(formatModelEffortTrace(null)).toBeNull();
  });

  it("2 — downgraded:false: degraded===false, texto sin flecha", () => {
    const f = formatModelEffortTrace({
      tool: "claude_code_cli",
      requested_model: "claude-sonnet-5",
      effective_model: "claude-sonnet-5",
      requested_effort: "high",
      effective_effort: "high",
      downgraded: false,
    });
    expect(f?.degraded).toBe(false);
    expect(f?.text).not.toContain("→");
  });

  it("3 — downgraded:true con max/high: degraded===true, texto contiene 'max → high'", () => {
    const f = formatModelEffortTrace({
      tool: "claude_code_cli",
      requested_effort: "max",
      effective_effort: "high",
      downgraded: true,
    });
    expect(f?.degraded).toBe(true);
    expect(f?.text).toContain("max → high");
  });

  it("4 — effort_mode no_aplica: el texto dice que la herramienta no usa esfuerzo", () => {
    const f = formatModelEffortTrace({
      tool: "github_copilot",
      effort_mode: "no_aplica",
      downgraded: true,
      reason: "github_copilot no expone niveles de esfuerzo",
    });
    expect(f?.text.toLowerCase()).toContain("no usa niveles de esfuerzo");
  });

  it("5 — deploy viejo (sin tool, sin effort_mode, CON downgraded): no lanza; tool '—'; degraded de downgraded", () => {
    const f = formatModelEffortTrace({
      requested_model: "claude-opus-4-8",
      effective_model: "claude-sonnet-5",
      downgraded: true,
    });
    expect(f).not.toBeNull();
    expect(f?.tool).toBe("—");
    expect(f?.degraded).toBe(true);
  });

  it("6 — [C8] presupuesto_turnos con effort_effective_now:false: avisa que quedó registrado, no cambió la corrida", () => {
    const f = formatModelEffortTrace({
      tool: "codex_cli",
      effort_mode: "presupuesto_turnos",
      effort_effective_now: false,
      requested_effort: "high",
      effective_effort: "high",
      downgraded: false,
    });
    expect(f?.text).toContain("quedó registrado");
    expect(f?.text).toContain("no cambia esta corrida");
  });
});

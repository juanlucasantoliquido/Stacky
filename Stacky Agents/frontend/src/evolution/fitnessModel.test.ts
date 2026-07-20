// Plan 168 F6 — tests puros del modelo Fitness (vitest node env, sin RTL/jsdom).
import { describe, it, expect } from "vitest";
import {
  levelLabel,
  levelTone,
  gateLabel,
  scoreDisplay,
  deltaDisplay,
  deltaTone,
  aspectLabel,
  canEvaluateProposal,
  judgeCheckLabel,
} from "./fitnessModel";

describe("fitnessModel", () => {
  it("levelLabel/levelTone los 3 niveles exactos", () => {
    expect(levelLabel("deterministic")).toBe("Determinista");
    expect(levelLabel("execution")).toBe("Ejecución");
    expect(levelLabel("llm_judge")).toBe("Juez LLM");
    expect(levelTone("deterministic")).toBe("success");
    expect(levelTone("execution")).toBe("info");
    expect(levelTone("llm_judge")).toBe("warning");
  });

  it("gateLabel los 3 valores", () => {
    expect(gateLabel("passed")).toBe("Deterministas OK");
    expect(gateLabel("failed")).toBe("Determinista FALLÓ");
    expect(gateLabel("none")).toBe("Sin deterministas");
  });

  it("scoreDisplay null y redondeo", () => {
    expect(scoreDisplay(null)).toBe("—");
    expect(scoreDisplay(0.8347)).toBe("0.83");
  });

  it("deltaDisplay positivo/negativo/cero/null con literales exactos", () => {
    expect(deltaDisplay(0.03)).toBe("▲ +0.03");
    expect(deltaDisplay(-0.05)).toBe("▼ -0.05");
    expect(deltaDisplay(0)).toBe("= 0.00");
    expect(deltaDisplay(null)).toBe("");
  });

  it("deltaTone los 3 tonos", () => {
    expect(deltaTone(0.1)).toBe("success");
    expect(deltaTone(-0.1)).toBe("danger");
    expect(deltaTone(0)).toBe("neutral");
    expect(deltaTone(null)).toBe("neutral");
  });

  it("aspectLabel las 3 formas", () => {
    expect(aspectLabel("agent_prompts/developer")).toBe("Prompt: developer");
    expect(aspectLabel("knowledge_rag")).toBe("Lecciones (RAG)");
    expect(aspectLabel("otra_cosa")).toBe("otra_cosa");
  });

  it("canEvaluateProposal tabla de verdad", () => {
    expect(canEvaluateProposal("prompt_file", "approved")).toBe(true);
    expect(canEvaluateProposal("free_text", "approved")).toBe(false);
    expect(canEvaluateProposal("prompt_file", "applied")).toBe(false);
  });

  it("bordes de formato (v2 C8)", () => {
    expect(scoreDisplay(0)).toBe("0.00");
    expect(deltaDisplay(0.0001)).toBe("▲ +0.00");
  });

  it("judgeCheckLabel los 4 valores exactos", () => {
    expect(judgeCheckLabel("calibrated")).toBe("Juez calibrado");
    expect(judgeCheckLabel("uncalibrated")).toBe("Juez descalibrado — no confiar en sus scores");
    expect(judgeCheckLabel("unavailable")).toBe("Juez no disponible");
    expect(judgeCheckLabel(null)).toBe("Juez sin verificar");
  });
});

import { describe, it, expect } from "vitest";
import {
  statusTone,
  statusLabel,
  loopModeLabel,
  filterProposals,
  availableActions,
  flagDeepLink,
  fitnessDisplay,
  type ProposalDto,
  type ProposalStatus,
} from "./model";

function mk(over: Partial<ProposalDto>): ProposalDto {
  return {
    id: "prop-1",
    aspect_id: "knowledge_rag",
    title: "t",
    rationale: "r",
    origin: "manual",
    artifact_type: "free_text",
    target_ref: null,
    proposed_content: null,
    base_hash: null,
    evidence: [],
    status: "draft",
    fitness_before: null,
    fitness_after: null,
    parent_proposal_id: null,
    cycle_id: null,
    snapshot_info: null,
    notes: [],
    created_at: "2026-07-18T00:00:00+00:00",
    updated_at: "2026-07-18T00:00:00+00:00",
    applied_at: null,
    rolled_back_at: null,
    ...over,
  };
}

const ALL_STATUSES: ProposalStatus[] = [
  "draft", "pending_review", "approved", "applied", "rejected", "rolled_back",
];

describe("model.ts — Centro de Evolución", () => {
  it("statusTone mapea los 6 estados", () => {
    expect(ALL_STATUSES.map(statusTone)).toEqual([
      "neutral", "info", "warning", "success", "danger", "neutral",
    ]);
  });

  it("statusLabel los 6 labels", () => {
    expect(ALL_STATUSES.map(statusLabel)).toEqual([
      "Borrador", "En revisión", "Aprobada", "Aplicada", "Rechazada", "Revertida",
    ]);
  });

  it("loopModeLabel los 2 labels", () => {
    expect(loopModeLabel("human_in_the_loop")).toBe("Humano en el lazo");
    expect(loopModeLabel("human_on_the_loop")).toBe("Humano sobre el lazo");
  });

  it("filterProposals por status", () => {
    const list = [mk({ id: "a", status: "draft" }), mk({ id: "b", status: "applied" })];
    const out = filterProposals(list, { status: "applied", aspectId: "TODOS", origin: "TODOS" });
    expect(out.map((p) => p.id)).toEqual(["b"]);
  });

  it("filterProposals por aspecto+origen combinados (AND)", () => {
    const list = [
      mk({ id: "a", aspect_id: "knowledge_rag", origin: "mape" }),
      mk({ id: "b", aspect_id: "knowledge_rag", origin: "manual" }),
      mk({ id: "c", aspect_id: "agent_prompts", origin: "mape" }),
    ];
    const out = filterProposals(list, { status: "TODAS", aspectId: "knowledge_rag", origin: "mape" });
    expect(out.map((p) => p.id)).toEqual(["a"]);
  });

  it("filterProposals TODAS/TODOS no filtra", () => {
    const list = [mk({ id: "a" }), mk({ id: "b", status: "applied" })];
    const out = filterProposals(list, { status: "TODAS", aspectId: "TODOS", origin: "TODOS" });
    expect(out.map((p) => p.id)).toEqual(["a", "b"]);
  });

  it("filterProposals no muta el input", () => {
    const list = [mk({ id: "a" }), mk({ id: "b", status: "applied" })];
    const snapshot = JSON.stringify(list);
    filterProposals(list, { status: "applied", aspectId: "TODOS", origin: "TODOS" });
    expect(JSON.stringify(list)).toBe(snapshot);
  });

  it("availableActions para los 6 estados", () => {
    expect(availableActions(mk({ status: "draft" })).map((a) => a.action)).toEqual([
      "submit", "reject",
    ]);
    expect(availableActions(mk({ status: "pending_review" })).map((a) => a.action)).toEqual([
      "approve", "reject",
    ]);
    // approved de free_text NO ofrece apply
    expect(
      availableActions(mk({ status: "approved", artifact_type: "free_text" })).map((a) => a.action),
    ).toEqual(["reject"]);
    // approved de knowledge_note SÍ ofrece apply
    expect(
      availableActions(mk({ status: "approved", artifact_type: "knowledge_note" })).map((a) => a.action),
    ).toEqual(["apply", "reject"]);
    // applied solo rollback con confirm true
    const applied = availableActions(mk({ status: "applied" }));
    expect(applied).toEqual([{ action: "rollback", label: "Revertir", confirm: true }]);
    expect(availableActions(mk({ status: "rejected" }))).toEqual([]);
    expect(availableActions(mk({ status: "rolled_back" }))).toEqual([]);
  });

  it("flagDeepLink", () => {
    expect(flagDeepLink("LOCAL_LLM_MODEL")).toBe("/settings?flag=LOCAL_LLM_MODEL");
    expect(flagDeepLink(null)).toBe(null);
  });

  it("fitnessDisplay placeholder visible, nunca inventado", () => {
    expect(fitnessDisplay(null)).toBe("—");
    expect(fitnessDisplay({ score: 0.5, metrics: {}, eval_ref: "e", evaluated_at: "now" })).toBe("0.5");
  });
});

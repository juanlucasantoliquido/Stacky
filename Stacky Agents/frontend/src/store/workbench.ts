import { create } from "zustand";
import type { AgentType, AgentWorkflowConfig, ContextBlock, Project, VsCodeAgent } from "../types";

interface WorkbenchState {
  activeTicketId: number | null;
  activeAgentType: AgentType | null;
  activeExecutionId: number | null;
  blocks: ContextBlock[];
  runningExecutionId: number | null;
  // FA-04 — modelo override (null = router decide)
  modelOverride: string | null;
  // FA-50 — system prompt override (null = default del agente)
  systemPromptOverride: string | null;
  // VS Code custom agent (null = ninguno seleccionado)
  vsCodeAgent: VsCodeAgent | null;
  activeProject: Project | null;
  /** Agentes fijados del proyecto activo */
  pinnedAgents: string[];
  /** Workflows por agente filename: { allowed_states, transition_state, requires_prior_output } */
  agentWorkflows: Record<string, AgentWorkflowConfig>;

  setActiveTicket: (id: number | null) => void;
  setActiveAgent: (t: AgentType | null) => void;
  setActiveExecution: (id: number | null) => void;
  setBlocks: (b: ContextBlock[]) => void;
  patchBlock: (id: string, patch: Partial<ContextBlock>) => void;
  removeBlock: (id: string) => void;
  setRunningExecution: (id: number | null) => void;
  setModelOverride: (m: string | null) => void;
  setSystemPromptOverride: (sp: string | null) => void;
  setVsCodeAgent: (a: VsCodeAgent | null) => void;
  setActiveProject: (p: Project | null) => void;
  setPinnedAgents: (agents: string[]) => void;
  setAgentWorkflows: (wf: Record<string, AgentWorkflowConfig>) => void;
}

export const useWorkbench = create<WorkbenchState>((set) => ({
  activeTicketId: null,
  activeAgentType: null,
  activeExecutionId: null,
  blocks: [],
  runningExecutionId: null,
  modelOverride: null,
  systemPromptOverride: null,
  vsCodeAgent: null,
  activeProject: null,
  pinnedAgents: [],
  agentWorkflows: {},

  setActiveTicket: (id) =>
    set({ activeTicketId: id, activeExecutionId: null, blocks: [] }),
  setActiveAgent: (t) =>
    set({
      activeAgentType: t,
      activeExecutionId: null,
      systemPromptOverride: null,
      vsCodeAgent: null,
    }),
  setActiveExecution: (id) => set({ activeExecutionId: id }),
  setBlocks: (b) => set({ blocks: b }),
  patchBlock: (id, patch) =>
    set((s) => ({
      blocks: s.blocks.map((b) => (b.id === id ? { ...b, ...patch } : b)),
    })),
  removeBlock: (id) =>
    set((s) => ({ blocks: s.blocks.filter((b) => b.id !== id) })),
  setRunningExecution: (id) => set({ runningExecutionId: id }),
  setModelOverride: (m) => set({ modelOverride: m }),
  setSystemPromptOverride: (sp) => set({ systemPromptOverride: sp }),
  setVsCodeAgent: (a) =>
    set({
      vsCodeAgent: a,
      activeAgentType: a ? "custom" : null,
      activeExecutionId: null,
      systemPromptOverride: a?.system_prompt ?? null,
    }),
  setActiveProject: (p) => set({ activeProject: p }),
  setPinnedAgents: (agents) => set({ pinnedAgents: agents }),
  setAgentWorkflows: (wf) => set({ agentWorkflows: wf }),
}));

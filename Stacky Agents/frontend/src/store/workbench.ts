import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { AgentRuntime, AgentType, AgentWorkflowConfig, ContextBlock, Project, VsCodeAgent } from "../types";

interface WorkbenchState {
  activeTicketId: number | null;
  activeAgentType: AgentType | null;
  activeExecutionId: number | null;
  codexConsoleExecutionId: number | null;
  codexConsoleMinimized: boolean;
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
  /** true mientras TopBar está cargando los agentes del proyecto activo */
  teamLoading: boolean;
  /** Mensaje de error de la última carga de agentes, null si no hubo error */
  getAgentsError: string | null;
  /** Runtime de ejecución seleccionado por el operador */
  agentRuntime: AgentRuntime;

  // P1.1 ChatDrawer state
  chatDrawerOpen: boolean;
  chatDrawerModel: string | null;
  chatDrawerTicketId: number | null;
  setChatDrawerOpen: (open: boolean) => void;
  setChatDrawerModel: (model: string | null) => void;
  setChatDrawerTicketId: (id: number | null) => void;

  setActiveTicket: (id: number | null) => void;
  setActiveAgent: (t: AgentType | null) => void;
  setActiveExecution: (id: number | null) => void;
  setCodexConsoleExecution: (id: number | null, minimized?: boolean) => void;
  setCodexConsoleMinimized: (value: boolean) => void;
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
  setTeamLoading: (loading: boolean) => void;
  setGetAgentsError: (err: string | null) => void;
  setAgentRuntime: (r: AgentRuntime) => void;
}

export const useWorkbench = create<WorkbenchState>()(
  persist(
    (set) => ({
  activeTicketId: null,
  activeAgentType: null,
  activeExecutionId: null,
  codexConsoleExecutionId: null,
  codexConsoleMinimized: false,
  blocks: [],
  runningExecutionId: null,
  modelOverride: null,
  systemPromptOverride: null,
  vsCodeAgent: null,
  activeProject: null,
  pinnedAgents: [],
  agentWorkflows: {},
  teamLoading: false,
  getAgentsError: null,
  // Plan 37 — default útil: Claude Code CLI (Copilot Free solo da Haiku).
  // El operador puede cambiarlo en el selector "Ejecutar con".
  agentRuntime: "claude_code_cli",

  // P1.1 ChatDrawer state
  chatDrawerOpen: false,
  chatDrawerModel: null,
  chatDrawerTicketId: null,

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
  setCodexConsoleExecution: (id, minimized = false) =>
    set({
      codexConsoleExecutionId: id,
      codexConsoleMinimized: id == null ? false : minimized,
    }),
  setCodexConsoleMinimized: (value) => set({ codexConsoleMinimized: value }),
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
  setTeamLoading: (loading) => set({ teamLoading: loading }),
  setGetAgentsError: (err) => set({ getAgentsError: err }),
  setAgentRuntime: (r) => set({ agentRuntime: r }),

  // P1.1 ChatDrawer actions
  setChatDrawerOpen: (open) => set({ chatDrawerOpen: open }),
  setChatDrawerModel: (model) => set({ chatDrawerModel: model }),
  setChatDrawerTicketId: (id) => set({ chatDrawerTicketId: id }),
    }),
    {
      name: "stacky-workbench",
      storage: createJSONStorage(() => localStorage),
      // Solo persistimos la preferencia de runtime: el resto del estado
      // (ticket activo, ejecuciones, bloques) es efímero por sesión y no
      // debe sobrevivir a una recarga.
      partialize: (state) => ({ agentRuntime: state.agentRuntime }),
      version: 2, // Plan 37 — default Claude Code CLI + remapeo del reset a Copilot del Plan 36
      migrate: (persisted: unknown, fromVersion: number) => {
        const valid: AgentRuntime[] = ["github_copilot", "codex_cli", "claude_code_cli"];
        const prev = (persisted ?? {}) as { agentRuntime?: unknown };
        let rt: AgentRuntime =
          typeof prev.agentRuntime === "string" && valid.includes(prev.agentRuntime as AgentRuntime)
            ? (prev.agentRuntime as AgentRuntime)
            : "claude_code_cli";
        // Plan 37 — el Plan 36 (v1) reseteó la preferencia persistida a
        // github_copilot, dejando operadores en Copilot Free (solo Haiku) sin
        // quererlo. En el salto v1→v2 remapeamos ese copilot heredado a Claude
        // Code CLI (default útil). Una elección explícita de Codex se preserva;
        // el operador puede volver a Copilot manualmente desde el selector.
        if (fromVersion < 2 && rt === "github_copilot") {
          rt = "claude_code_cli";
        }
        return { agentRuntime: rt };
      },
    }
  )
);

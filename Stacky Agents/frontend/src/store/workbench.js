import { create } from "zustand";
export const useWorkbench = create((set) => ({
    activeTicketId: null,
    activeAgentType: null,
    activeExecutionId: null,
    blocks: [],
    runningExecutionId: null,
    modelOverride: null,
    systemPromptOverride: null,
    vsCodeAgent: null,
    setActiveTicket: (id) => set({ activeTicketId: id, activeExecutionId: null, blocks: [] }),
    setActiveAgent: (t) => set({
        activeAgentType: t,
        activeExecutionId: null,
        systemPromptOverride: null,
        vsCodeAgent: null,
    }),
    setActiveExecution: (id) => set({ activeExecutionId: id }),
    setBlocks: (b) => set({ blocks: b }),
    patchBlock: (id, patch) => set((s) => ({
        blocks: s.blocks.map((b) => (b.id === id ? { ...b, ...patch } : b)),
    })),
    removeBlock: (id) => set((s) => ({ blocks: s.blocks.filter((b) => b.id !== id) })),
    setRunningExecution: (id) => set({ runningExecutionId: id }),
    setModelOverride: (m) => set({ modelOverride: m }),
    setSystemPromptOverride: (sp) => set({ systemPromptOverride: sp }),
    setVsCodeAgent: (a) => set({
        vsCodeAgent: a,
        activeAgentType: a ? "custom" : null,
        activeExecutionId: null,
        systemPromptOverride: a?.system_prompt ?? null,
    }),
}));

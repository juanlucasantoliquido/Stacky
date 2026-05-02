import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from "react";
import { useAgentRun } from "../hooks/useAgentRun";
import { useOpenChat } from "../hooks/useOpenChat";
import { useWorkbench } from "../store/workbench";
import CostPreview from "./CostPreview";
import ModelPicker from "./ModelPicker";
import RunButton from "./RunButton";
import SimilarPanel from "./SimilarPanel";
import SystemPromptDrawer from "./SystemPromptDrawer";
import TokenCounter from "./TokenCounter";
import styles from "./InputContextEditor.module.css";
const TOKEN_LIMIT = 200_000;
export default function InputContextEditor() {
    const { activeTicketId, activeAgentType, blocks, patchBlock, removeBlock, runningExecutionId, vsCodeAgent, } = useWorkbench();
    const run = useAgentRun();
    const openChat = useOpenChat();
    const tokens = useMemo(() => estimateTokens(blocks), [blocks]);
    const canRun = activeTicketId != null &&
        activeAgentType != null &&
        blocks.length > 0 &&
        tokens < TOKEN_LIMIT &&
        runningExecutionId == null &&
        !run.isPending &&
        (activeAgentType !== "custom" || vsCodeAgent != null);
    const canOpenChat = activeTicketId != null &&
        vsCodeAgent != null &&
        blocks.length > 0 &&
        !openChat.isPending;
    if (!activeTicketId) {
        return (_jsxs("div", { className: styles.empty, children: [_jsx("h2", { children: "Seleccion\u00E1 un ticket" }), _jsx("p", { className: "muted", children: "Stacky Agents es un workbench: vos eleg\u00EDs el ticket, vos eleg\u00EDs el agente, vos lo corr\u00E9s." })] }));
    }
    if (!activeAgentType) {
        return (_jsxs("div", { className: styles.empty, children: [_jsx("h2", { children: "Eleg\u00ED un agente" }), _jsx("p", { className: "muted", children: "Cada agente es independiente. Pod\u00E9s correrlos en cualquier orden." })] }));
    }
    const headerLabel = activeAgentType === "custom" && vsCodeAgent
        ? `${vsCodeAgent.name} (copilot agent)`
        : activeAgentType;
    return (_jsxs("div", { className: styles.editor, children: [_jsxs("header", { className: styles.head, children: [_jsxs("div", { children: [_jsxs("div", { className: styles.title, children: ["INPUT CONTEXT \u2014 ", headerLabel] }), _jsxs("div", { className: "muted", children: ["ticket #", activeTicketId] })] }), _jsx("div", { className: styles.headRight, children: _jsx(ModelPicker, { agentType: activeAgentType, blocks: blocks }) })] }), _jsx(SystemPromptDrawer, { agentType: activeAgentType }), _jsx(SimilarPanel, {}), _jsx("div", { className: styles.blocks, children: blocks.map((b) => (_jsx(BlockView, { block: b, onChange: (content) => patchBlock(b.id, { content }), onToggleItem: (idx) => {
                        if (b.kind !== "choice" || !b.items)
                            return;
                        const items = b.items.map((it, i) => i === idx ? { ...it, selected: !it.selected } : it);
                        patchBlock(b.id, { items });
                    }, onRemove: () => removeBlock(b.id) }, b.id))) }), _jsxs("footer", { className: styles.foot, children: [_jsxs("div", { className: styles.footLeft, children: [_jsx(TokenCounter, { current: tokens, max: TOKEN_LIMIT }), _jsx(CostPreview, { agentType: activeAgentType, blocks: blocks })] }), _jsxs("div", { className: styles.footRight, children: [vsCodeAgent && (_jsx("button", { className: styles.chatBtn, disabled: !canOpenChat, title: "Abrir en Copilot Chat con el agente y contexto pre-cargados", onClick: () => {
                                    openChat.mutate({
                                        ticket_id: activeTicketId,
                                        context_blocks: blocks,
                                    });
                                }, children: openChat.isPending ? "Abriendo…" : "↗ Abrir en Chat" })), _jsx(RunButton, { state: run.isPending || runningExecutionId != null ? "running" : "idle", disabled: !canRun, onClick: () => {
                                    run.mutate({
                                        agent_type: activeAgentType,
                                        ticket_id: activeTicketId,
                                        context_blocks: blocks,
                                    });
                                } })] })] })] }));
}
function BlockView({ block, onChange, onToggleItem, onRemove, }) {
    return (_jsxs("div", { className: styles.block, children: [_jsxs("div", { className: styles.blockHead, children: [_jsx("span", { className: styles.blockTitle, children: block.title }), _jsxs("span", { className: styles.blockKind, children: ["[", block.kind, "]"] }), _jsx("button", { className: styles.x, onClick: onRemove, title: "Sacar bloque", children: "\u00D7" })] }), block.kind === "editable" && (_jsx("textarea", { className: styles.textarea, rows: 4, placeholder: "Escrib\u00ED notas, restricciones, prioridades\u2026", value: block.content ?? "", onChange: (e) => onChange(e.target.value) })), block.kind === "auto" && (_jsx("pre", { className: styles.auto, children: block.content })), block.kind === "choice" && block.items && (_jsx("ul", { className: styles.choices, children: block.items.map((it, idx) => (_jsx("li", { children: _jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: it.selected, onChange: () => onToggleItem(idx) }), " ", it.label] }) }, idx))) }))] }));
}
function estimateTokens(blocks) {
    let chars = 0;
    for (const b of blocks) {
        if (b.content)
            chars += b.content.length;
        if (b.items)
            chars += b.items.filter((x) => x.selected).reduce((s, x) => s + x.label.length, 0);
    }
    return Math.ceil(chars / 4);
}

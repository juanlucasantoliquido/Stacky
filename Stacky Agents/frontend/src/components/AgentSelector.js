import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useQuery } from "@tanstack/react-query";
import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { colorForAgent } from "./AgentCard";
import card from "./AgentCard.module.css";
import styles from "./AgentSelector.module.css";
export default function AgentSelector() {
    const { vsCodeAgent, setVsCodeAgent } = useWorkbench();
    const { data: vscode, isLoading, error, refetch, isFetching, } = useQuery({
        queryKey: ["vscode-agents"],
        queryFn: Agents.vsCodeAgents,
        staleTime: 60_000,
    });
    const list = vscode ?? [];
    return (_jsxs("section", { className: styles.section, children: [_jsxs("div", { className: styles.header, children: [_jsx("h3", { className: styles.title, children: "AGENTES" }), _jsxs("button", { type: "button", className: styles.refresh, onClick: () => refetch(), disabled: isFetching, title: "Recargar agentes desde la carpeta de prompts de VS Code", children: [isFetching ? "↻" : "⟳", " ", isFetching ? "Cargando…" : "Recargar"] })] }), isLoading && _jsx("div", { className: styles.empty, children: "cargando agentes\u2026" }), error && (_jsx("div", { className: styles.empty, children: "error cargando agentes de VS Code" })), !isLoading && !error && list.length === 0 && (_jsxs("div", { className: styles.empty, children: ["No hay archivos ", _jsx("code", { children: ".agent.md" }), " en la carpeta de prompts de VS Code."] })), _jsx("div", { className: styles.list, children: list.map((a) => (_jsx(VsCodeAgentRow, { agent: a, selected: vsCodeAgent?.filename === a.filename, onSelect: () => setVsCodeAgent(a) }, a.filename))) })] }));
}
function VsCodeAgentRow({ agent, selected, onSelect, }) {
    const desc = agent.description.length > 140
        ? agent.description.slice(0, 140) + "…"
        : agent.description;
    const style = { "--agent-color": colorForAgent("custom") };
    return (_jsxs("button", { className: `${card.card} ${selected ? card.selected : ""}`, onClick: onSelect, title: agent.description, style: style, "data-agent": "custom", children: [_jsxs("div", { className: card.head, children: [_jsx("span", { className: card.icon, children: "\u2726" }), _jsx("span", { className: card.name, children: agent.name })] }), desc && _jsx("div", { className: card.desc, children: desc })] }));
}

import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import styles from "./AgentCard.module.css";
const AGENT_COLORS = {
    business: "var(--agent-business)",
    functional: "var(--agent-functional)",
    technical: "var(--agent-technical)",
    developer: "var(--agent-developer)",
    qa: "var(--agent-qa)",
    custom: "var(--agent-custom)",
};
export function colorForAgent(type) {
    if (!type)
        return "var(--agent-custom)";
    return AGENT_COLORS[type] ?? "var(--agent-custom)";
}
export default function AgentCard({ agent, selected, onSelect }) {
    const style = { "--agent-color": colorForAgent(agent.type) };
    return (_jsxs("button", { className: `${styles.card} ${selected ? styles.selected : ""}`, onClick: onSelect, title: agent.description, style: style, "data-agent": agent.type, children: [_jsxs("div", { className: styles.head, children: [_jsx("span", { className: styles.icon, children: agent.icon || "•" }), _jsx("span", { className: styles.name, children: agent.name })] }), _jsx("div", { className: styles.desc, children: agent.description }), _jsxs("div", { className: styles.meta, children: [_jsx("span", { className: "muted", children: "in:" }), " ", agent.inputs.slice(0, 2).join(", ")] })] }));
}

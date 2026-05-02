import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { getAgentAvatar, getAgentNickname, getAgentRole, removePinnedAgent, } from "../services/preferences";
import PixelAvatar from "./PixelAvatar";
import AgentLaunchModal from "./AgentLaunchModal";
import styles from "./EmployeeCard.module.css";
const AGENT_TYPE_COLORS = {
    business: "var(--agent-business)",
    functional: "var(--agent-functional)",
    technical: "var(--agent-technical)",
    developer: "var(--agent-developer)",
    qa: "var(--agent-qa)",
    custom: "var(--agent-custom)",
};
function inferType(filename) {
    const f = filename.toLowerCase();
    if (f.includes("business") || f.includes("negocio"))
        return "business";
    if (f.includes("functional") || f.includes("funcional"))
        return "functional";
    if (f.includes("technical") || f.includes("tecnic"))
        return "technical";
    if (f.includes("dev") || f.includes("desarrollador"))
        return "developer";
    if (f.includes("qa") || f.includes("test"))
        return "qa";
    return "custom";
}
export default function EmployeeCard({ filename, agent, onEdit, onRemoved }) {
    const [menuOpen, setMenuOpen] = useState(false);
    const [launchOpen, setLaunchOpen] = useState(false);
    const nickname = getAgentNickname(filename);
    const role = getAgentRole(filename);
    const avatar = getAgentAvatar(filename);
    const type = inferType(filename);
    const color = AGENT_TYPE_COLORS[type] ?? AGENT_TYPE_COLORS.custom;
    const displayName = nickname ?? agent?.name ?? filename.replace(/\.agent\.md$/i, "");
    const displayRole = role ?? agent?.description?.split(".")[0] ?? "Agente VS Code";
    return (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.card, style: { "--agent-color": color }, children: [_jsx("div", { className: styles.typeBadge, style: { background: color }, children: type }), _jsxs("div", { className: styles.menuWrapper, children: [_jsx("button", { className: styles.kebab, onClick: (e) => { e.stopPropagation(); setMenuOpen((o) => !o); }, title: "Opciones", children: "\u22EE" }), menuOpen && (_jsxs("div", { className: styles.menu, onMouseLeave: () => setMenuOpen(false), children: [_jsx("button", { onClick: () => { setMenuOpen(false); onEdit(filename); }, children: "\u270F\uFE0F Editar empleado" }), _jsx("button", { className: styles.menuDanger, onClick: () => { setMenuOpen(false); removePinnedAgent(filename); onRemoved(); }, children: "\uD83D\uDDD1\uFE0F Quitar del equipo" })] }))] }), _jsx("div", { className: styles.avatarWrap, children: _jsx(PixelAvatar, { value: avatar, size: "lg", name: displayName }) }), _jsx("div", { className: styles.name, children: displayName }), _jsx("div", { className: styles.role, children: displayRole }), _jsx("button", { className: styles.assignBtn, onClick: () => setLaunchOpen(true), children: "Asignar Ticket \u2192" })] }), launchOpen && (_jsx(AgentLaunchModal, { agent: agent ?? { name: displayName, filename, description: displayRole, system_prompt: "" }, avatarValue: avatar, onClose: () => setLaunchOpen(false) }))] }));
}

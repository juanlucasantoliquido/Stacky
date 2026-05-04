import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useCallback } from "react";
import { Agents } from "../api/endpoints";
import { getPinnedAgents } from "../services/preferences";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import styles from "./TeamScreen.module.css";
export default function TeamScreen({ onGoToWorkbench }) {
    const [allAgents, setAllAgents] = useState([]);
    const [pinned, setPinned] = useState(getPinnedAgents());
    const [manageOpen, setManageOpen] = useState(false);
    const [editTarget, setEditTarget] = useState(null);
    const [loading, setLoading] = useState(true);
    const refresh = useCallback(() => {
        setPinned([...getPinnedAgents()]);
    }, []);
    useEffect(() => {
        Agents.vsCodeAgents()
            .then(setAllAgents)
            .catch(() => setAllAgents([]))
            .finally(() => setLoading(false));
    }, []);
    function agentByFilename(filename) {
        return allAgents.find((a) => a.filename === filename);
    }
    return (_jsxs("div", { className: styles.root, children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.headerLeft, children: [_jsx("span", { className: styles.logo, children: "\u26A1" }), _jsx("h1", { className: styles.title, children: "Tu Equipo" }), pinned.length > 0 && (_jsxs("span", { className: styles.count, children: [pinned.length, " agente", pinned.length !== 1 ? "s" : ""] }))] }), _jsxs("div", { className: styles.headerActions, children: [_jsx("button", { className: styles.addBtn, onClick: () => setManageOpen(true), children: "+ Agregar empleado" }), _jsx("button", { className: styles.workbenchBtn, onClick: onGoToWorkbench, children: "Ir al Workbench \u2192" })] })] }), _jsx("main", { className: styles.main, children: loading ? (_jsx("div", { className: styles.loading, children: "Cargando agentes\u2026" })) : pinned.length === 0 ? (_jsx(EmptyState, { onAdd: () => setManageOpen(true) })) : (_jsx("div", { className: styles.grid, children: pinned.map((filename) => (_jsx(EmployeeCard, { filename: filename, agent: agentByFilename(filename), onEdit: (f) => setEditTarget(f), onRemoved: refresh }, filename))) })) }), manageOpen && (_jsx(TeamManageDrawer, { allAgents: allAgents, onClose: () => { setManageOpen(false); refresh(); } })), editTarget && (_jsx(EmployeeEditDrawer, { filename: editTarget, agent: agentByFilename(editTarget), onClose: () => { setEditTarget(null); refresh(); }, onRemoved: () => { setEditTarget(null); refresh(); } }))] }));
}
function EmptyState({ onAdd }) {
    return (_jsxs("div", { className: styles.empty, children: [_jsx("div", { className: styles.emptyIcon, children: "\uD83D\uDC65" }), _jsx("h2", { className: styles.emptyTitle, children: "Tu equipo est\u00E1 vac\u00EDo" }), _jsx("p", { className: styles.emptyText, children: "Agreg\u00E1 tu primer agente para empezar a asignar tickets desde aqu\u00ED." }), _jsx("button", { className: styles.emptyBtn, onClick: onAdd, children: "+ Agregar primer agente" })] }));
}

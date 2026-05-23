import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Agents, Projects, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { useRunningStatus } from "../hooks/useRunningStatus";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import styles from "./TeamScreen.module.css";
export default function TeamScreen() {
    const [allAgents, setAllAgents] = useState([]);
    const [manageOpen, setManageOpen] = useState(false);
    const [editTarget, setEditTarget] = useState(null);
    const [loading, setLoading] = useState(true);
    // ─── Fuente de verdad: store, no localStorage ──────────────────────────────
    const activeProject = useWorkbench((s) => s.activeProject);
    const activeProjectName = activeProject?.name ?? null;
    const pinned = useWorkbench((s) => s.pinnedAgents);
    const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
    const teamLoading = useWorkbench((s) => s.teamLoading);
    const getAgentsError = useWorkbench((s) => s.getAgentsError);
    const [removeError, setRemoveError] = useState(null);
    /** Quita un empleado del proyecto activo vía API y actualiza el store. */
    async function handleRemoveEmployee(filename) {
        if (!activeProject)
            return;
        const nextPinned = pinned.filter((f) => f !== filename);
        setRemoveError(null);
        try {
            await Projects.putAgents(activeProject.name, nextPinned);
            setPinnedAgents(nextPinned);
        }
        catch {
            setRemoveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
        }
    }
    // Running status — quién está trabajando ahora
    const { runningByTicket } = useRunningStatus();
    const { data: tickets } = useQuery({
        queryKey: ["tickets", activeProjectName],
        queryFn: () => Tickets.list(activeProjectName),
        staleTime: 60_000,
    });
    const ticketById = useMemo(() => new Map((tickets ?? []).map((t) => [t.id, t])), [tickets]);
    // Map: inferred agent type → running execution (first match)
    const runningByAgentType = useMemo(() => {
        const map = new Map();
        for (const exec of runningByTicket.values()) {
            if (!map.has(exec.agent_type))
                map.set(exec.agent_type, exec);
        }
        return map;
    }, [runningByTicket]);
    useEffect(() => {
        Agents.vsCodeAgents()
            .then(setAllAgents)
            .catch(() => setAllAgents([]))
            .finally(() => setLoading(false));
    }, []);
    function agentByFilename(filename) {
        return allAgents.find((a) => a.filename === filename);
    }
    function inferAgentType(filename) {
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
    return (_jsxs("div", { className: styles.root, children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.headerLeft, children: [_jsx("span", { className: styles.logo, children: "\u26A1" }), _jsx("h1", { className: styles.title, children: "Tu Equipo" }), pinned.length > 0 && (_jsxs("span", { className: styles.count, children: [pinned.length, " agente", pinned.length !== 1 ? "s" : ""] }))] }), _jsx("div", { className: styles.headerActions, children: _jsx("button", { className: styles.addBtn, onClick: () => setManageOpen(true), disabled: !activeProject, title: !activeProject ? "Seleccioná un proyecto primero" : undefined, children: "+ Agregar empleado" }) })] }), _jsxs("main", { className: styles.main, children: [removeError && (_jsxs("div", { className: styles.errorBanner, role: "alert", children: ["\u26A0 ", removeError] })), getAgentsError && (_jsxs("div", { className: styles.errorBanner, role: "alert", children: ["\u26A0 ", getAgentsError] })), loading || teamLoading ? (_jsx("div", { className: styles.loadingGrid, children: [...Array(4)].map((_, i) => (_jsx("div", { className: styles.skeletonCard, "aria-hidden": "true" }, i))) })) : !activeProject ? (_jsx(NoProjectState, {})) : pinned.length === 0 ? (_jsx(EmptyState, { onAdd: () => setManageOpen(true) })) : (_jsx("div", { className: styles.grid, children: pinned.map((filename) => {
                            const agentType = inferAgentType(filename);
                            const runningExec = runningByAgentType.get(agentType) ?? null;
                            const runningAdoId = runningExec
                                ? (ticketById.get(runningExec.ticket_id)?.ado_id ?? null)
                                : null;
                            return (_jsx(EmployeeCard, { filename: filename, agent: agentByFilename(filename), runningExecution: runningExec, runningTicketAdoId: runningAdoId, onEdit: (f) => setEditTarget(f), onRemoved: () => handleRemoveEmployee(filename) }, filename));
                        }) }))] }), manageOpen && (_jsx(TeamManageDrawer, { allAgents: allAgents, onClose: () => setManageOpen(false) })), editTarget && (_jsx(EmployeeEditDrawer, { filename: editTarget, agent: agentByFilename(editTarget), onClose: () => setEditTarget(null), onRemoved: () => { setEditTarget(null); handleRemoveEmployee(editTarget); } }))] }));
}
function NoProjectState() {
    return (_jsxs("div", { className: styles.empty, children: [_jsx("div", { className: styles.emptyIcon, children: "\uD83D\uDCC2" }), _jsx("h2", { className: styles.emptyTitle, children: "Ning\u00FAn proyecto activo" }), _jsx("p", { className: styles.emptyText, children: "Seleccion\u00E1 un proyecto desde la barra superior para ver su equipo." })] }));
}
function EmptyState({ onAdd }) {
    return (_jsxs("div", { className: styles.empty, children: [_jsx("div", { className: styles.emptyIcon, children: "\uD83D\uDC65" }), _jsx("h2", { className: styles.emptyTitle, children: "Tu equipo est\u00E1 vac\u00EDo" }), _jsx("p", { className: styles.emptyText, children: "Agreg\u00E1 tu primer agente para empezar a asignar tickets desde aqu\u00ED." }), _jsx("button", { className: styles.emptyBtn, onClick: onAdd, children: "+ Agregar primer agente" })] }));
}

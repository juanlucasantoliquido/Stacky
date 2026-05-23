import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, FlowConfig } from "../api/endpoints";
import AgentRuntimeSelector from "../components/AgentRuntimeSelector";
import { useTicketSync } from "../hooks/useTicketSync";
import { SyncStatusBar } from "../components/SyncStatusBar";
import TicketGraphView from "../components/TicketGraphView";
import RecoverExecutionButton from "../components/RecoverExecutionButton";
import FinishWorkButton from "../components/FinishWorkButton";
import CreateChildTaskButton from "../components/CreateChildTaskButton";
import { useRunningStatus } from "../hooks/useRunningStatus";
import { getAgentType } from "../services/preferences";
import { findVsCodeAgent, humanizeAgentLaunchError, launchAgentWithRuntime, launchInProgressLabel, runtimeRequiresVsCodeAgent, } from "../services/agentLaunch";
import { useWorkbench } from "../store/workbench";
import { detectInconsistencyFromRunning } from "../utils/inconsistencyDetector";
import styles from "./TicketBoard.module.css";
// Resuelve el tipo del agente. Prioriza el override explícito que el operador
// fija en EmployeeEditDrawer; cae a heurística sobre el filename si no hay override.
function inferType(filename) {
    const override = getAgentType(filename);
    if (override)
        return override;
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
// Encuentra el filename del agente configurado en el equipo que coincide con el tipo.
// Primero busca en los agentes pinneados (el equipo del operador), luego en todos.
function findAgentFilenameByType(agentType, vsCodeAgents, pinnedFilenames) {
    const pinnedMatch = pinnedFilenames.find((f) => inferType(f) === agentType);
    if (pinnedMatch)
        return pinnedMatch;
    const anyMatch = vsCodeAgents.find((a) => inferType(a.filename) === agentType);
    return anyMatch?.filename ?? null;
}
const ADO_STATE_COLORS = {
    "Active": "#3b82f6",
    "In Progress": "#3b82f6",
    "En Progreso": "#3b82f6",
    "Resolved": "#a855f7",
    "Committed": "#f59e0b",
    "New": "#6b7280",
    "Done": "#22c55e",
    "Closed": "#22c55e",
};
const CLOSED_STATES = ["Done", "Closed", "Resolved", "Removed", "Completed"];
const NEXT_AGENT_LABELS = {
    business: "💼 Negocio",
    functional: "🔍 Funcional",
    technical: "🔬 Técnico",
    developer: "🚀 Dev",
    qa: "✅ QA",
};
function stateColor(state) {
    if (!state)
        return "#6b7280";
    return ADO_STATE_COLORS[state] ?? "#6b7280";
}
function RunModal({ ticket, mode, suggestedLabel, suggestedFilename, vsCodeAgents, isLaunching, errorMessage, onConfirm, onClose, }) {
    const agentRuntime = useWorkbench((s) => s.agentRuntime);
    const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
    const [note, setNote] = useState("");
    const [selectedFilename, setSelectedFilename] = useState(vsCodeAgents[0]?.filename ?? "");
    const resolvedFilename = mode === "custom" ? (selectedFilename || null) : suggestedFilename;
    const canConfirm = (mode === "suggested" ? !!suggestedLabel : !!selectedFilename) &&
        (!runtimeRequiresVsCodeAgent(agentRuntime) || !!resolvedFilename);
    return (_jsx("div", { className: styles.modalOverlay, onClick: onClose, children: _jsxs("div", { className: styles.modal, onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: styles.modalHeader, children: [_jsx("span", { className: styles.modalIcon, children: mode === "suggested" ? "🤖" : "⚙️" }), _jsxs("div", { className: styles.modalTitleBlock, children: [_jsx("div", { className: styles.modalTitle, children: mode === "suggested" ? "Run Sugerido" : "Run Personalizado" }), _jsxs("div", { className: styles.modalSub, children: ["ADO-", ticket.ado_id, " \u00B7 ", ticket.title.length > 48 ? ticket.title.slice(0, 48) + "…" : ticket.title] })] }), _jsx("button", { className: styles.modalClose, onClick: onClose, children: "\u2715" })] }), mode === "suggested" && suggestedLabel && (_jsxs("div", { className: styles.modalAgentRow, children: [_jsx("span", { className: styles.modalAgentIcon, children: "\u25B6" }), _jsx("span", { className: styles.modalAgentName, children: suggestedLabel }), suggestedFilename ? (_jsx("span", { className: styles.modalAgentHint, children: suggestedFilename.replace(/\.agent\.md$/i, "") })) : (_jsx("span", { className: styles.modalAgentHint, children: "sin agente asignado en equipo" }))] })), mode === "custom" && (_jsxs("div", { className: styles.modalSection, children: [_jsx("label", { className: styles.modalLabel, children: "Agente" }), vsCodeAgents.length === 0 ? (_jsx("p", { className: styles.modalEmpty, children: "No hay agentes configurados en VS Code." })) : (_jsx("select", { className: styles.modalSelect, value: selectedFilename, onChange: (e) => setSelectedFilename(e.target.value), children: vsCodeAgents.map((a) => (_jsx("option", { value: a.filename, children: a.name }, a.filename))) }))] })), _jsxs("div", { className: styles.modalSection, children: [_jsx(AgentRuntimeSelector, { value: agentRuntime, onChange: setAgentRuntime, disabled: isLaunching }), runtimeRequiresVsCodeAgent(agentRuntime) && !resolvedFilename && (_jsx("p", { className: styles.modalEmpty, children: "Este runtime necesita un agente VS Code asignado para el ticket seleccionado." }))] }), _jsxs("div", { className: styles.modalSection, children: [_jsxs("label", { className: styles.modalLabel, children: ["Nota para el agente ", _jsx("span", { className: styles.modalOptional, children: "(opcional)" })] }), _jsx("textarea", { className: styles.modalTextarea, placeholder: "Instrucciones adicionales, contexto o aclaraciones para incluir en el chat de VS Code\u2026", value: note, onChange: (e) => setNote(e.target.value), rows: 4, autoFocus: true })] }), errorMessage && (_jsx("div", { className: styles.modalError, role: "alert", children: errorMessage })), _jsxs("div", { className: styles.modalActions, children: [_jsx("button", { className: styles.modalCancel, onClick: onClose, disabled: isLaunching, children: "Cancelar" }), _jsx("button", { className: styles.modalConfirm, onClick: () => onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : suggestedFilename), disabled: isLaunching || !canConfirm, children: isLaunching ? launchInProgressLabel(agentRuntime) : "▶ Ejecutar" })] })] }) }));
}
function TicketCard({ ticket, runningExecution, vsCodeAgents, flowConfigMap, indent }) {
    const qc = useQueryClient();
    const agentRuntime = useWorkbench((s) => s.agentRuntime);
    const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
    const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
    const [expanded, setExpanded] = useState(false);
    const [runModal, setRunModal] = useState(null);
    const [isLaunching, setIsLaunching] = useState(false);
    const [launchError, setLaunchError] = useState(null);
    // Feature #4: la inferencia LLM (Tickets.adoPipelineStatus) fue removida del
    // consumo del frontend porque devolvía sugerencias poco confiables. La
    // recomendación viene 100% de FlowConfig (mapping determinístico). El
    // endpoint backend sigue existiendo para rollback.
    // #7: Tasks nunca proponen Negocio — ya tienen análisis funcional
    // #8: Épicas nunca proponen Negocio — tienen su propio botón Funcional
    const isTask = (ticket.work_item_type ?? "").toLowerCase() === "task";
    const isEpic = (ticket.work_item_type ?? "").toLowerCase() === "epic";
    // Feature #4 — recomendación determinística desde FlowConfig (DO-4.1: clave agent_type).
    // Se resuelve desde el map cargado una vez en TicketBoard raíz; no hay llamada por ticket.
    // Si el estado ADO no tiene regla configurada, nextSuggested es null → botón deshabilitado.
    const rawFlowAgentType = ticket.ado_state
        ? (flowConfigMap.get(ticket.ado_state.trim().toLowerCase()) ?? null)
        : null;
    // Preservar regla de negocio #7/#8: Tasks y Épicas nunca proponen Negocio
    const nextSuggested = ((isTask || isEpic) && rawFlowAgentType === "business") ? null : rawFlowAgentType;
    const nextLabel = nextSuggested ? (NEXT_AGENT_LABELS[nextSuggested] ?? nextSuggested) : null;
    // Resuelve el filename del agente del equipo que corresponde al tipo sugerido.
    // Prioriza agentes pinneados ("Tu Equipo") sobre cualquier agente disponible.
    const suggestedFilename = nextSuggested
        ? findAgentFilenameByType(nextSuggested, vsCodeAgents, pinnedAgents)
        : null;
    const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "");
    // Fuente dual: AgentExecution activa (prop) O stacky_status del ticket (BD)
    const isRunning = !isClosed && (!!runningExecution || ticket.stacky_status === "running");
    const runningAgentType = runningExecution?.agent_type ?? null;
    // Detección de estado INCONSISTENTE: stacky_status=completed + ejecución huérfana activa
    const inconsistency = detectInconsistencyFromRunning(ticket.stacky_status, runningExecution ?? null);
    const handleRunConfirm = useCallback(async (note, filename) => {
        setIsLaunching(true);
        setLaunchError(null);
        try {
            const contextBlocks = note
                ? [{ id: "operator-note", kind: "editable", title: "Nota del operador", content: note }]
                : [];
            await launchAgentWithRuntime({
                ticketId: ticket.id,
                projectName: activeProjectName,
                runtime: agentRuntime,
                contextBlocks,
                vscodeAgent: findVsCodeAgent(vsCodeAgents, filename),
            });
            await Promise.all([
                qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
                qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
                qc.invalidateQueries({ queryKey: ["executions"] }),
            ]);
            setRunModal(null);
        }
        catch (error) {
            setLaunchError(humanizeAgentLaunchError(error));
        }
        finally {
            setIsLaunching(false);
        }
    }, [activeProjectName, agentRuntime, pinnedAgents, qc, ticket.id, vsCodeAgents]);
    return (_jsxs(_Fragment, { children: [_jsxs("div", { className: `${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""} ${indent ? styles.cardIndented : ""}`, children: [inconsistency.isInconsistent ? (_jsxs("div", { className: styles.runningCardBanner, style: { background: "rgba(245,158,11,0.18)", borderColor: "rgba(245,158,11,0.45)" }, children: [_jsx("span", { className: "badge-inconsistente", children: "INCONSISTENTE" }), _jsxs("span", { style: { fontSize: 11, color: "rgba(255,255,255,0.6)", marginLeft: 6 }, children: ["ejecuci\u00F3n #", inconsistency.orphanExecution.id, " hu\u00E9rfana"] })] })) : isRunning && (_jsxs("div", { className: styles.runningCardBanner, children: [_jsx("span", { className: styles.runningPulse }), _jsx("span", { children: "EN EJECUCI\u00D3N" }), runningAgentType && (_jsx("span", { className: styles.runningCardAgent, children: runningAgentType }))] })), _jsxs("div", { className: styles.cardHeader, onClick: () => setExpanded((x) => !x), children: [_jsxs("div", { className: styles.cardTop, children: [_jsxs("span", { className: styles.adoId, children: ["ADO-", ticket.ado_id] }), _jsx("span", { className: styles.stateBadge, style: { background: `${stateColor(ticket.ado_state)}22`, color: stateColor(ticket.ado_state), border: `1px solid ${stateColor(ticket.ado_state)}44` }, children: ticket.ado_state ?? "—" }), ticket.priority != null && (_jsxs("span", { className: styles.priority, children: ["P", ticket.priority] }))] }), _jsx("p", { className: styles.cardTitle, children: ticket.title }), _jsx("div", { className: styles.cardActions, onClick: (e) => e.stopPropagation(), children: nextLabel && _jsxs("span", { className: styles.nextTag, children: ["\u2192 ", nextLabel] }) })] }), expanded && (_jsxs("div", { className: styles.cardBody, children: [inconsistency.isInconsistent && ticket.ado_id && (_jsx("div", { style: { marginBottom: 8 }, onClick: (e) => e.stopPropagation(), children: _jsx(RecoverExecutionButton, { adoId: ticket.ado_id, ticketId: ticket.id, orphanExecution: inconsistency.orphanExecution }) })), isRunning && !inconsistency.isInconsistent && (_jsx("div", { style: { marginBottom: 8 }, onClick: (e) => e.stopPropagation(), children: _jsx(FinishWorkButton, { ticket: ticket, onCompleted: () => {
                                        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
                                        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
                                    } }) })), isEpic && (_jsx("div", { style: { marginBottom: 8 }, onClick: (e) => e.stopPropagation(), children: _jsx(CreateChildTaskButton, { epicAdoId: ticket.ado_id, disabled: isRunning, onTaskCreated: () => {
                                        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
                                        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
                                    } }) })), _jsxs("div", { className: styles.runButtons, children: [_jsxs("button", { className: styles.runSuggestedBtn, onClick: (e) => { e.stopPropagation(); setLaunchError(null); setRunModal("suggested"); }, disabled: !nextSuggested || isRunning, title: isRunning
                                            ? "Hay un agente corriendo sobre este ticket — esperá a que termine"
                                            : nextSuggested
                                                ? `Correr agente sugerido: ${nextLabel}`
                                                : ticket.ado_state
                                                    ? `No hay agente configurado para el estado '${ticket.ado_state}'. Configurá el flujo en la pestaña Config de Flujo.`
                                                    : "El ticket no tiene estado ADO asignado.", children: ["\u25B6 Run Sugerido", nextLabel && _jsx("span", { className: styles.runBtnHint, children: nextLabel })] }), _jsx("button", { className: styles.runCustomBtn, onClick: (e) => { e.stopPropagation(); setLaunchError(null); setRunModal("custom"); }, disabled: isRunning, title: isRunning ? "Hay un agente corriendo sobre este ticket" : undefined, children: "\u2699 Run Custom" })] }), ticket.description && (_jsxs("details", { className: styles.descDetails, children: [_jsx("summary", { children: "Descripci\u00F3n" }), _jsx("p", { className: styles.descText, children: ticket.description })] })), ticket.ado_url && (_jsx("a", { className: styles.adoLink, href: ticket.ado_url, target: "_blank", rel: "noreferrer", onClick: (e) => e.stopPropagation(), children: "Abrir en Azure DevOps \u2197" }))] }))] }), runModal && (_jsx(RunModal, { ticket: ticket, mode: runModal, suggestedLabel: nextLabel, suggestedFilename: suggestedFilename, vsCodeAgents: vsCodeAgents, isLaunching: isLaunching, errorMessage: launchError, onConfirm: handleRunConfirm, onClose: () => setRunModal(null) }))] }));
}
function EpicGroup({ epic, runningByTicket, vsCodeAgents, flowConfigMap }) {
    const qc = useQueryClient();
    const agentRuntime = useWorkbench((s) => s.agentRuntime);
    const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
    const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
    const [collapsed, setCollapsed] = useState(false);
    const [isLaunching, setIsLaunching] = useState(false);
    const [launchError, setLaunchError] = useState(null);
    const isClosed = CLOSED_STATES.includes(epic.ado_state ?? "");
    const runningExec = runningByTicket.get(epic.id) ?? null;
    const isRunning = !isClosed && !!runningExec;
    const functionalFilename = findAgentFilenameByType("functional", vsCodeAgents, pinnedAgents);
    const handleRunFunctional = useCallback(async (e) => {
        e.stopPropagation();
        if (!functionalFilename)
            return;
        setIsLaunching(true);
        setLaunchError(null);
        try {
            await launchAgentWithRuntime({
                ticketId: epic.id,
                projectName: activeProjectName,
                runtime: agentRuntime,
                contextBlocks: [],
                vscodeAgent: findVsCodeAgent(vsCodeAgents, functionalFilename),
            });
            await Promise.all([
                qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
                qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
                qc.invalidateQueries({ queryKey: ["executions"] }),
            ]);
        }
        catch (error) {
            setLaunchError(humanizeAgentLaunchError(error));
        }
        finally {
            setIsLaunching(false);
        }
    }, [activeProjectName, agentRuntime, epic.id, functionalFilename, pinnedAgents, qc, vsCodeAgents]);
    return (_jsxs("div", { className: styles.epicGroup, children: [_jsxs("div", { className: `${styles.epicHeader} ${isClosed ? styles.epicClosed : ""}`, children: [_jsx("button", { className: styles.epicCollapseBtn, onClick: () => setCollapsed((x) => !x), title: collapsed ? "Expandir" : "Colapsar", children: collapsed ? "▶" : "▼" }), _jsx("span", { className: styles.epicBadge, children: "EPIC" }), _jsxs("span", { className: styles.epicAdoId, children: ["ADO-", epic.ado_id] }), _jsx("span", { className: styles.epicState, style: { color: stateColor(epic.ado_state), borderColor: `${stateColor(epic.ado_state)}44` }, children: epic.ado_state ?? "—" }), _jsx("span", { className: styles.epicTitle, children: epic.title }), _jsxs("span", { className: styles.epicChildCount, children: [epic.children.length, " item", epic.children.length !== 1 ? "s" : ""] }), runningExec && !isClosed && (_jsxs("span", { className: styles.epicRunningChip, children: [_jsx("span", { className: styles.runningPulse }), " EN EJECUCI\u00D3N"] })), epic.ado_url && (_jsx("a", { className: styles.epicAdoLink, href: epic.ado_url, target: "_blank", rel: "noreferrer", onClick: (e) => e.stopPropagation(), children: "\u2197" })), !isClosed && (_jsx("button", { className: styles.epicRunBtn, onClick: handleRunFunctional, disabled: isLaunching || isRunning || !functionalFilename, title: isRunning
                            ? "Hay un agente corriendo sobre esta épica"
                            : !functionalFilename
                                ? "No hay agente funcional configurado en el equipo"
                                : `Correr agente Funcional: ${functionalFilename?.replace(/\.agent\.md$/i, "")}`, children: isLaunching ? "⏳" : "🔍 Funcional" }))] }), launchError && (_jsx("div", { style: { marginTop: 8, fontSize: 11, color: "#fca5a5" }, children: launchError })), !collapsed && (_jsx("div", { className: styles.epicChildren, children: epic.children.length === 0 ? (_jsx("div", { className: styles.epicNoChildren, children: "Sin tareas asociadas" })) : (epic.children.map((child) => (_jsx(TicketCard, { ticket: child, runningExecution: runningByTicket.get(child.id) ?? null, vsCodeAgents: vsCodeAgents, flowConfigMap: flowConfigMap, indent: true }, child.id)))) }))] }));
}
// ─── TicketBoard (página principal) ──────────────────────────────────────────
export default function TicketBoard() {
    const qc = useQueryClient();
    const [search, setSearch] = useState("");
    const [onlyPending, setOnlyPending] = useState(false);
    const [viewMode, setViewMode] = useState("graph");
    // #3: Filtro de estados por agente activo
    const vsCodeAgent = useWorkbench((s) => s.vsCodeAgent);
    const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
    const agentRuntime = useWorkbench((s) => s.agentRuntime);
    const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
    const activeProject = useWorkbench((s) => s.activeProject);
    const activeProjectName = activeProject?.name ?? null;
    const activeAllowedStates = vsCodeAgent
        ? (agentWorkflows[vsCodeAgent.filename]?.allowed_states ?? [])
        : [];
    // Hook centralizado de estado running (fuente dual: stacky_status + executions polling)
    const { runningByTicket, runningTicketIds, getRunningTickets } = useRunningStatus();
    // P7: hook de auto-refresh con Page Visibility API y backoff
    const { lastSyncedAt, secondsSinceSync, isSyncing: isSyncingV2, syncError: syncErrorV2, triggerSync, isStale, } = useTicketSync({ intervalMs: 45_000, syncOnMount: true });
    const { data: tickets, isLoading } = useQuery({
        queryKey: ["tickets", activeProjectName],
        queryFn: () => Tickets.list(activeProjectName),
        refetchInterval: 45_000,
        staleTime: 22_500,
        refetchOnWindowFocus: true,
    });
    const { data: hierarchy, isLoading: isHierarchyLoading } = useQuery({
        queryKey: ["tickets-hierarchy", activeProjectName],
        queryFn: () => Tickets.hierarchy(activeProjectName),
        refetchInterval: 45_000,
        staleTime: 22_500,
        enabled: viewMode === "tree" || viewMode === "graph",
    });
    // VsCode agents para el dropdown de Run Custom
    const { data: vsCodeAgents } = useQuery({
        queryKey: ["vscode-agents"],
        queryFn: Agents.vsCodeAgents,
        staleTime: 5 * 60 * 1000,
    });
    // Feature #4 — FlowConfig: cargar reglas una vez y construir map ado_state→agent_type.
    // La lista completa de reglas es chica (4-10 en práctica), no se llama resolve por ticket.
    const { data: flowConfigData } = useQuery({
        queryKey: ["flow-config", activeProjectName],
        queryFn: () => FlowConfig.list(activeProjectName),
        staleTime: 5 * 60 * 1000,
    });
    // Keys normalizadas a lowercase para que la resolución no dependa del casing
    // del estado ADO sincronizado (ej. "Technical review" vs "Technical Review").
    const flowConfigMap = useMemo(() => {
        const map = new Map();
        for (const rule of flowConfigData?.rules ?? []) {
            map.set(rule.ado_state.trim().toLowerCase(), rule.agent_type);
        }
        return map;
    }, [flowConfigData]);
    // Filtrado para vista jerárquica (filtra dentro de epics + orphans)
    function filterNode(node) {
        if (search) {
            const q = search.toLowerCase();
            const selfMatch = node.title.toLowerCase().includes(q) || String(node.ado_id).includes(q);
            const childMatch = node.children.some((c) => filterNode(c));
            if (!selfMatch && !childMatch)
                return false;
        }
        if (onlyPending && CLOSED_STATES.includes(node.ado_state ?? ""))
            return false;
        // #3: si el agente activo tiene allowed_states, filtrar por estado
        if (activeAllowedStates.length > 0 && !activeAllowedStates.includes(node.ado_state ?? "")) {
            // Pero si tiene hijos que sí aplican, mostrar el nodo padre igual
            const childMatch = node.children.some((c) => activeAllowedStates.includes(c.ado_state ?? ""));
            if (!childMatch)
                return false;
        }
        return true;
    }
    const filteredEpics = (hierarchy?.epics ?? []).filter(filterNode);
    const filteredOrphans = (hierarchy?.orphans ?? []).filter((n) => filterNode(n));
    const totalHierarchy = filteredEpics.length + filteredOrphans.length;
    // Tickets activos (no cerrados) con ejecución en curso
    const runningTickets = getRunningTickets((tickets ?? []).filter((t) => !CLOSED_STATES.includes(t.ado_state ?? "")));
    return (_jsxs("div", { className: styles.root, children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.headerLeft, children: [_jsx("span", { className: styles.logo, children: "\uD83D\uDCCB" }), _jsx("h1", { className: styles.title, children: "Tickets ADO" }), viewMode === "tree" && (_jsxs("span", { className: styles.count, children: [totalHierarchy, " grupos"] })), viewMode === "graph" && hierarchy && (_jsxs("span", { className: styles.count, children: [hierarchy.epics.length, " \u00E9picas \u00B7 ", hierarchy.epics.reduce((a, e) => a + e.children.length, 0) + hierarchy.orphans.length, " tareas"] })), runningTicketIds.size > 0 && (_jsxs("span", { className: styles.headerRunningCount, title: `${runningTicketIds.size} ticket(s) con agente en ejecución`, children: [_jsx("span", { className: styles.headerRunningDot }), runningTicketIds.size, " corriendo"] }))] }), _jsxs("div", { className: styles.headerActions, children: [_jsxs("div", { className: styles.viewToggle, children: [_jsx("button", { className: `${styles.viewToggleBtn} ${viewMode === "tree" ? styles.viewToggleActive : ""}`, onClick: () => setViewMode("tree"), title: "Vista jer\u00E1rquica Epic \u2192 Tasks", children: "\uD83C\uDF33 Jer\u00E1rquica" }), _jsx("button", { className: `${styles.viewToggleBtn} ${viewMode === "graph" ? styles.viewToggleActive : ""}`, onClick: () => setViewMode("graph"), title: "Vista grafo Epic \u2192 Tasks con conexiones visuales", children: "\uD83D\uDD17 Grafo" })] }), _jsx(AgentRuntimeSelector, { value: agentRuntime, onChange: setAgentRuntime }), _jsxs("label", { className: styles.filterToggle, children: [_jsx("input", { type: "checkbox", checked: onlyPending, onChange: (e) => setOnlyPending(e.target.checked) }), "Solo abiertos"] }), syncErrorV2 && (_jsxs("div", { style: { color: "#fff", background: "#b91c1c", padding: "6px 12px", borderRadius: 6, marginBottom: 8, maxWidth: 340, fontSize: 15, fontWeight: 500 }, children: [_jsx("span", { style: { marginRight: 8 }, children: "\u26A0\uFE0F" }), syncErrorV2] })), _jsx("button", { className: styles.syncBtn, onClick: triggerSync, disabled: isSyncingV2, title: "Sincronizar tickets desde ADO", children: isSyncingV2 ? "↻ Sincronizando…" : "⟳ Sincronizar ADO" })] })] }), _jsx(SyncStatusBar, { lastSyncedAt: lastSyncedAt, secondsSinceSync: secondsSinceSync, isSyncing: isSyncingV2, syncError: syncErrorV2, onSyncClick: triggerSync, isStale: isStale, intervalMs: 45_000 }), runningTickets.length > 0 && (_jsxs("div", { className: styles.activeExecutionsBanner, children: [_jsx("span", { className: styles.activeExecPulse }), _jsx("span", { className: styles.activeExecTitle, children: runningTickets.length === 1
                            ? "1 ticket en ejecución"
                            : `${runningTickets.length} tickets en ejecución` }), _jsx("div", { className: styles.activeExecChips, children: runningTickets.map((t) => {
                            const exec = runningByTicket.get(t.id);
                            return (_jsxs("span", { className: styles.activeExecChip, children: ["ADO-", t.ado_id, exec && _jsx("span", { className: styles.activeExecChipAgent, children: exec.agent_type }), _jsxs("span", { className: styles.activeExecChipTitle, children: [t.title.slice(0, 28), t.title.length > 28 ? "…" : ""] })] }, t.id));
                        }) })] })), activeAllowedStates.length > 0 && vsCodeAgent && (_jsxs("div", { style: { background: "#1e3a5f", color: "#7dd3fc", padding: "6px 16px", fontSize: 13, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #2563eb44" }, children: [_jsxs("span", { children: ["\uD83E\uDD16 ", vsCodeAgent.name] }), _jsx("span", { style: { color: "#94a3b8" }, children: "mostrando solo estados:" }), activeAllowedStates.map((s) => (_jsx("span", { style: { background: "#2563eb33", border: "1px solid #3b82f6", borderRadius: 4, padding: "1px 8px" }, children: s }, s)))] })), _jsx("div", { className: styles.searchBar, children: _jsx("input", { className: styles.searchInput, placeholder: "Buscar por t\u00EDtulo o ADO-ID\u2026", value: search, onChange: (e) => setSearch(e.target.value) }) }), _jsxs("main", { className: styles.main, children: [viewMode === "tree" && (_jsxs(_Fragment, { children: [isHierarchyLoading && _jsx("div", { className: styles.loading, children: "Cargando jerarqu\u00EDa\u2026" }), !isHierarchyLoading && filteredEpics.length === 0 && filteredOrphans.length === 0 && (_jsx("div", { className: styles.empty, children: "No hay tickets. Hac\u00E9 clic en \u00ABSincronizar ADO\u00BB." })), _jsxs("div", { className: styles.treeView, children: [filteredEpics.map((epic) => (_jsx(EpicGroup, { epic: epic, runningByTicket: runningByTicket, vsCodeAgents: vsCodeAgents ?? [], flowConfigMap: flowConfigMap }, epic.id))), filteredOrphans.length > 0 && (_jsxs("div", { className: styles.orphanSection, children: [_jsxs("div", { className: styles.orphanHeader, children: [_jsx("span", { className: styles.orphanBadge, children: "SIN EPIC" }), _jsxs("span", { className: styles.orphanCount, children: [filteredOrphans.length, " item", filteredOrphans.length !== 1 ? "s" : ""] })] }), _jsx("div", { className: styles.orphanGrid, children: filteredOrphans.map((t) => (_jsx(TicketCard, { ticket: t, runningExecution: runningByTicket.get(t.id) ?? null, vsCodeAgents: vsCodeAgents ?? [], flowConfigMap: flowConfigMap }, t.id))) })] }))] })] })), viewMode === "graph" && (_jsxs(_Fragment, { children: [isHierarchyLoading && _jsx("div", { className: styles.loading, children: "Cargando grafo\u2026" }), !isHierarchyLoading && (_jsx(TicketGraphView, { hierarchy: hierarchy ?? null, onSync: triggerSync, isSyncing: isSyncingV2, syncError: syncErrorV2, vsCodeAgents: vsCodeAgents ?? [], runningByTicket: runningByTicket }))] }))] })] }));
}

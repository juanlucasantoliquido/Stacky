import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, Executions } from "../api/endpoints";
import PipelineStatus from "../components/PipelineStatus";
import TicketGraphView from "../components/TicketGraphView";
import { getPinnedAgents } from "../services/preferences";
import styles from "./TicketBoard.module.css";
// Infiere el tipo de agente desde el filename — misma lógica que EmployeeCard.
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
function RunModal({ ticket, mode, suggestedLabel, suggestedFilename, vsCodeAgents, isLaunching, onConfirm, onClose }) {
    const [note, setNote] = useState("");
    const [selectedFilename, setSelectedFilename] = useState(vsCodeAgents[0]?.filename ?? "");
    const canConfirm = mode === "suggested"
        ? !!suggestedLabel
        : !!selectedFilename;
    return (_jsx("div", { className: styles.modalOverlay, onClick: onClose, children: _jsxs("div", { className: styles.modal, onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: styles.modalHeader, children: [_jsx("span", { className: styles.modalIcon, children: mode === "suggested" ? "🤖" : "⚙️" }), _jsxs("div", { className: styles.modalTitleBlock, children: [_jsx("div", { className: styles.modalTitle, children: mode === "suggested" ? "Run Sugerido" : "Run Personalizado" }), _jsxs("div", { className: styles.modalSub, children: ["ADO-", ticket.ado_id, " \u00B7 ", ticket.title.length > 48 ? ticket.title.slice(0, 48) + "…" : ticket.title] })] }), _jsx("button", { className: styles.modalClose, onClick: onClose, children: "\u2715" })] }), mode === "suggested" && suggestedLabel && (_jsxs("div", { className: styles.modalAgentRow, children: [_jsx("span", { className: styles.modalAgentIcon, children: "\u25B6" }), _jsx("span", { className: styles.modalAgentName, children: suggestedLabel }), suggestedFilename ? (_jsx("span", { className: styles.modalAgentHint, children: suggestedFilename.replace(/\.agent\.md$/i, "") })) : (_jsx("span", { className: styles.modalAgentHint, children: "sin agente asignado en equipo" }))] })), mode === "custom" && (_jsxs("div", { className: styles.modalSection, children: [_jsx("label", { className: styles.modalLabel, children: "Agente" }), vsCodeAgents.length === 0 ? (_jsx("p", { className: styles.modalEmpty, children: "No hay agentes configurados en VS Code." })) : (_jsx("select", { className: styles.modalSelect, value: selectedFilename, onChange: (e) => setSelectedFilename(e.target.value), children: vsCodeAgents.map((a) => (_jsx("option", { value: a.filename, children: a.name }, a.filename))) }))] })), _jsxs("div", { className: styles.modalSection, children: [_jsxs("label", { className: styles.modalLabel, children: ["Nota para el agente ", _jsx("span", { className: styles.modalOptional, children: "(opcional)" })] }), _jsx("textarea", { className: styles.modalTextarea, placeholder: "Instrucciones adicionales, contexto o aclaraciones para incluir en el chat de VS Code\u2026", value: note, onChange: (e) => setNote(e.target.value), rows: 4, autoFocus: true })] }), _jsxs("div", { className: styles.modalActions, children: [_jsx("button", { className: styles.modalCancel, onClick: onClose, disabled: isLaunching, children: "Cancelar" }), _jsx("button", { className: styles.modalConfirm, onClick: () => onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : suggestedFilename), disabled: isLaunching || !canConfirm, children: isLaunching ? "⏳ Abriendo chat…" : "▶ Ejecutar" })] })] }) }));
}
function TicketCard({ ticket, runningExecution, vsCodeAgents, indent }) {
    const qc = useQueryClient();
    const [expanded, setExpanded] = useState(false);
    const [runModal, setRunModal] = useState(null);
    const [isLaunching, setIsLaunching] = useState(false);
    const inferenceKey = ["ado-pipeline", ticket.id];
    const { data: inference, isFetching, isError } = useQuery({
        queryKey: inferenceKey,
        queryFn: () => Tickets.adoPipelineStatus(ticket.id),
        staleTime: 55 * 60 * 1000,
        retry: false,
        enabled: false,
    });
    const inferMutation = useMutation({
        mutationFn: (force) => Tickets.adoPipelineStatus(ticket.id, force),
        onSuccess: (data) => {
            qc.setQueryData(inferenceKey, data);
        },
    });
    const handleRefresh = useCallback((e) => {
        e.stopPropagation();
        inferMutation.mutate(true);
    }, [inferMutation]);
    // Auto-trigger inference when card first expands and no result exists yet
    useEffect(() => {
        if (expanded && !result && !inferMutation.isPending && !isFetching) {
            inferMutation.mutate(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [expanded]);
    const isLoading = isFetching || inferMutation.isPending;
    const result = inference ?? (inferMutation.data ?? null);
    const nextSuggested = result?.next_suggested ?? null;
    const nextLabel = nextSuggested ? (NEXT_AGENT_LABELS[nextSuggested] ?? nextSuggested) : null;
    // Resuelve el filename del agente del equipo que corresponde al tipo sugerido.
    // Prioriza agentes pinneados ("Tu Equipo") sobre cualquier agente disponible.
    const suggestedFilename = nextSuggested
        ? findAgentFilenameByType(nextSuggested, vsCodeAgents, getPinnedAgents())
        : null;
    const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "");
    const isRunning = !!runningExecution && !isClosed;
    const handleRunConfirm = useCallback(async (note, filename) => {
        setIsLaunching(true);
        try {
            const contextBlocks = note
                ? [{ id: "operator-note", kind: "editable", title: "Nota del operador", content: note }]
                : [];
            await Agents.openChat({
                ticket_id: ticket.id,
                context_blocks: contextBlocks,
                vscode_agent_filename: filename ?? undefined,
            });
            setRunModal(null);
        }
        finally {
            setIsLaunching(false);
        }
    }, [ticket.id]);
    return (_jsxs(_Fragment, { children: [_jsxs("div", { className: `${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""} ${indent ? styles.cardIndented : ""}`, children: [isRunning && (_jsxs("div", { className: styles.runningCardBanner, children: [_jsx("span", { className: styles.runningPulse }), _jsx("span", { children: "EN EJECUCI\u00D3N" })] })), _jsxs("div", { className: styles.cardHeader, onClick: () => setExpanded((x) => !x), children: [_jsxs("div", { className: styles.cardTop, children: [_jsxs("span", { className: styles.adoId, children: ["ADO-", ticket.ado_id] }), _jsx("span", { className: styles.stateBadge, style: { background: `${stateColor(ticket.ado_state)}22`, color: stateColor(ticket.ado_state), border: `1px solid ${stateColor(ticket.ado_state)}44` }, children: ticket.ado_state ?? "—" }), ticket.priority != null && (_jsxs("span", { className: styles.priority, children: ["P", ticket.priority] }))] }), _jsx("p", { className: styles.cardTitle, children: ticket.title }), result && !expanded && (_jsx("div", { className: styles.pipelineInline, children: _jsx(PipelineStatus, { result: result, compact: true }) })), _jsxs("div", { className: styles.cardActions, onClick: (e) => e.stopPropagation(), children: [isLoading && _jsx("span", { className: styles.inferring, children: "\u23F3 Analizando\u2026" }), result && !isLoading && (_jsxs(_Fragment, { children: [nextLabel && _jsxs("span", { className: styles.nextTag, children: ["\u2192 ", nextLabel] }), _jsx("button", { className: styles.refreshBtn, onClick: handleRefresh, title: "Re-inferir ignorando cache", children: "\u27F3" })] })), isError && _jsx("span", { className: styles.errorTag, children: "\u26A0 Error al inferir" })] })] }), expanded && (_jsxs("div", { className: styles.cardBody, children: [result ? (_jsx(PipelineStatus, { result: result })) : (_jsx("div", { className: styles.noInference, children: isLoading ? "Consultando ADO + LLM…" : "Analizando pipeline…" })), _jsxs("div", { className: styles.runButtons, children: [_jsxs("button", { className: styles.runSuggestedBtn, onClick: (e) => { e.stopPropagation(); setRunModal("suggested"); }, disabled: !nextSuggested, title: nextSuggested ? `Correr agente sugerido: ${nextLabel}` : "Esperando inferencia de pipeline…", children: ["\u25B6 Run Sugerido", nextLabel && _jsx("span", { className: styles.runBtnHint, children: nextLabel })] }), _jsx("button", { className: styles.runCustomBtn, onClick: (e) => { e.stopPropagation(); setRunModal("custom"); }, children: "\u2699 Run Custom" })] }), ticket.description && (_jsxs("details", { className: styles.descDetails, children: [_jsx("summary", { children: "Descripci\u00F3n" }), _jsx("p", { className: styles.descText, children: ticket.description })] })), ticket.ado_url && (_jsx("a", { className: styles.adoLink, href: ticket.ado_url, target: "_blank", rel: "noreferrer", onClick: (e) => e.stopPropagation(), children: "Abrir en Azure DevOps \u2197" }))] }))] }), runModal && (_jsx(RunModal, { ticket: ticket, mode: runModal, suggestedLabel: nextLabel, suggestedFilename: suggestedFilename, vsCodeAgents: vsCodeAgents, isLaunching: isLaunching, onConfirm: handleRunConfirm, onClose: () => setRunModal(null) }))] }));
}
function EpicGroup({ epic, runningByTicket, vsCodeAgents }) {
    const [collapsed, setCollapsed] = useState(false);
    const [isLaunching, setIsLaunching] = useState(false);
    const isClosed = CLOSED_STATES.includes(epic.ado_state ?? "");
    const runningExec = runningByTicket.get(epic.id) ?? null;
    const isRunning = !isClosed && !!runningExec;
    const functionalFilename = findAgentFilenameByType("functional", vsCodeAgents, getPinnedAgents());
    const handleRunFunctional = useCallback(async (e) => {
        e.stopPropagation();
        if (!functionalFilename)
            return;
        setIsLaunching(true);
        try {
            await Agents.openChat({
                ticket_id: epic.id,
                context_blocks: [],
                vscode_agent_filename: functionalFilename,
            });
        }
        finally {
            setIsLaunching(false);
        }
    }, [epic.id, functionalFilename]);
    return (_jsxs("div", { className: styles.epicGroup, children: [_jsxs("div", { className: `${styles.epicHeader} ${isClosed ? styles.epicClosed : ""}`, children: [_jsx("button", { className: styles.epicCollapseBtn, onClick: () => setCollapsed((x) => !x), title: collapsed ? "Expandir" : "Colapsar", children: collapsed ? "▶" : "▼" }), _jsx("span", { className: styles.epicBadge, children: "EPIC" }), _jsxs("span", { className: styles.epicAdoId, children: ["ADO-", epic.ado_id] }), _jsx("span", { className: styles.epicState, style: { color: stateColor(epic.ado_state), borderColor: `${stateColor(epic.ado_state)}44` }, children: epic.ado_state ?? "—" }), _jsx("span", { className: styles.epicTitle, children: epic.title }), _jsxs("span", { className: styles.epicChildCount, children: [epic.children.length, " item", epic.children.length !== 1 ? "s" : ""] }), runningExec && !isClosed && (_jsxs("span", { className: styles.epicRunningChip, children: [_jsx("span", { className: styles.runningPulse }), " EN EJECUCI\u00D3N"] })), epic.ado_url && (_jsx("a", { className: styles.epicAdoLink, href: epic.ado_url, target: "_blank", rel: "noreferrer", onClick: (e) => e.stopPropagation(), children: "\u2197" })), !isClosed && (_jsx("button", { className: styles.epicRunBtn, onClick: handleRunFunctional, disabled: isLaunching || isRunning || !functionalFilename, title: isRunning ? "Hay un agente corriendo sobre esta \u00E9pica" : !functionalFilename ? "No hay agente funcional configurado en el equipo" : `Correr agente Funcional: ${functionalFilename?.replace(/\.agent\.md$/i, "")}`, children: isLaunching ? "\u23F3" : "\uD83D\uDD0D Funcional" }))] }), !collapsed && (_jsx("div", { className: styles.epicChildren, children: epic.children.length === 0 ? (_jsx("div", { className: styles.epicNoChildren, children: "Sin tareas asociadas" })) : (epic.children.map((child) => (_jsx(TicketCard, { ticket: child, runningExecution: runningByTicket.get(child.id) ?? null, vsCodeAgents: vsCodeAgents, indent: true }, child.id)))) }))] }));
}
// ─── TicketBoard (página principal) ──────────────────────────────────────────
export default function TicketBoard() {
    const qc = useQueryClient();
    const [search, setSearch] = useState("");
    const [onlyPending, setOnlyPending] = useState(false);
    const [viewMode, setViewMode] = useState("tree");
    const { data: tickets, isLoading } = useQuery({
        queryKey: ["tickets"],
        queryFn: Tickets.list,
        refetchInterval: 60_000,
    });
    const { data: hierarchy, isLoading: isHierarchyLoading } = useQuery({
        queryKey: ["tickets-hierarchy"],
        queryFn: Tickets.hierarchy,
        refetchInterval: 60_000,
        enabled: viewMode === "tree" || viewMode === "graph",
    });
    // Polling de ejecuciones activas cada 5 segundos
    const { data: activeExecs } = useQuery({
        queryKey: ["executions-active"],
        queryFn: () => Executions.list({ status: "running" }),
        refetchInterval: 5_000,
        staleTime: 0,
    });
    const { data: queuedExecs } = useQuery({
        queryKey: ["executions-queued"],
        queryFn: () => Executions.list({ status: "queued" }),
        refetchInterval: 5_000,
        staleTime: 0,
    });
    // VsCode agents para el dropdown de Run Custom
    const { data: vsCodeAgents } = useQuery({
        queryKey: ["vscode-agents"],
        queryFn: Agents.vsCodeAgents,
        staleTime: 5 * 60 * 1000,
    });
    const syncMutation = useMutation({
        mutationFn: Tickets.sync,
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["tickets"] });
            qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
        },
    });
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
        return true;
    }
    const filteredEpics = (hierarchy?.epics ?? []).filter(filterNode);
    const filteredOrphans = (hierarchy?.orphans ?? []).filter((n) => filterNode(n));
    const totalHierarchy = filteredEpics.length + filteredOrphans.length;
    // Map ticketId -> running execution
    const runningByTicket = new Map();
    [...(activeExecs ?? []), ...(queuedExecs ?? [])].forEach((e) => {
        if (!runningByTicket.has(e.ticket_id)) {
            runningByTicket.set(e.ticket_id, e);
        }
    });
    // Tickets activos (no cerrados) con ejecución en curso
    const runningTickets = (tickets ?? []).filter((t) => runningByTicket.has(t.id) && !CLOSED_STATES.includes(t.ado_state ?? ""));
    return (_jsxs("div", { className: styles.root, children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.headerLeft, children: [_jsx("span", { className: styles.logo, children: "\uD83D\uDCCB" }), _jsx("h1", { className: styles.title, children: "Tickets ADO" }), viewMode === "tree" && (_jsxs("span", { className: styles.count, children: [totalHierarchy, " grupos"] })), viewMode === "graph" && hierarchy && (_jsxs("span", { className: styles.count, children: [hierarchy.epics.length, " \u00E9picas \u00B7 ", hierarchy.epics.reduce((a, e) => a + e.children.length, 0) + hierarchy.orphans.length, " tareas"] }))] }), _jsxs("div", { className: styles.headerActions, children: [_jsxs("div", { className: styles.viewToggle, children: [_jsx("button", { className: `${styles.viewToggleBtn} ${viewMode === "tree" ? styles.viewToggleActive : ""}`, onClick: () => setViewMode("tree"), title: "Vista jer\u00E1rquica Epic \u2192 Tasks", children: "\uD83C\uDF33 Jer\u00E1rquica" }), _jsx("button", { className: `${styles.viewToggleBtn} ${viewMode === "graph" ? styles.viewToggleActive : ""}`, onClick: () => setViewMode("graph"), title: "Vista grafo Epic \u2192 Tasks con conexiones visuales", children: "\uD83D\uDD17 Grafo" })] }), _jsxs("label", { className: styles.filterToggle, children: [_jsx("input", { type: "checkbox", checked: onlyPending, onChange: (e) => setOnlyPending(e.target.checked) }), "Solo abiertos"] }), _jsx("button", { className: styles.syncBtn, onClick: () => syncMutation.mutate(), disabled: syncMutation.isPending, title: "Sincronizar tickets desde ADO", children: syncMutation.isPending ? "↻ Sincronizando…" : "⟳ Sincronizar ADO" })] })] }), runningTickets.length > 0 && (_jsxs("div", { className: styles.activeExecutionsBanner, children: [_jsx("span", { className: styles.activeExecPulse }), _jsx("span", { className: styles.activeExecTitle, children: runningTickets.length === 1
                            ? "1 ticket en ejecución"
                            : `${runningTickets.length} tickets en ejecución` }), _jsx("div", { className: styles.activeExecChips, children: runningTickets.map((t) => (_jsxs("span", { className: styles.activeExecChip, children: ["ADO-", t.ado_id, _jsxs("span", { className: styles.activeExecChipTitle, children: [t.title.slice(0, 30), t.title.length > 30 ? "…" : ""] })] }, t.id))) })] })), _jsx("div", { className: styles.searchBar, children: _jsx("input", { className: styles.searchInput, placeholder: "Buscar por t\u00EDtulo o ADO-ID\u2026", value: search, onChange: (e) => setSearch(e.target.value) }) }), _jsxs("main", { className: styles.main, children: [viewMode === "tree" && (_jsxs(_Fragment, { children: [isHierarchyLoading && _jsx("div", { className: styles.loading, children: "Cargando jerarqu\u00EDa\u2026" }), !isHierarchyLoading && filteredEpics.length === 0 && filteredOrphans.length === 0 && (_jsx("div", { className: styles.empty, children: "No hay tickets. Hac\u00E9 clic en \u00ABSincronizar ADO\u00BB." })), _jsxs("div", { className: styles.treeView, children: [filteredEpics.map((epic) => (_jsx(EpicGroup, { epic: epic, runningByTicket: runningByTicket, vsCodeAgents: vsCodeAgents ?? [] }, epic.id))), filteredOrphans.length > 0 && (_jsxs("div", { className: styles.orphanSection, children: [_jsxs("div", { className: styles.orphanHeader, children: [_jsx("span", { className: styles.orphanBadge, children: "SIN EPIC" }), _jsxs("span", { className: styles.orphanCount, children: [filteredOrphans.length, " item", filteredOrphans.length !== 1 ? "s" : ""] })] }), _jsx("div", { className: styles.orphanGrid, children: filteredOrphans.map((t) => (_jsx(TicketCard, { ticket: t, runningExecution: runningByTicket.get(t.id) ?? null, vsCodeAgents: vsCodeAgents ?? [] }, t.id))) })] }))] })] })), viewMode === "graph" && (_jsxs(_Fragment, { children: [isHierarchyLoading && _jsx("div", { className: styles.loading, children: "Cargando grafo\u2026" }), !isHierarchyLoading && (_jsx(TicketGraphView, { hierarchy: hierarchy ?? null, onSync: () => syncMutation.mutate(), isSyncing: syncMutation.isPending, vsCodeAgents: vsCodeAgents ?? [], runningByTicket: runningByTicket }))] }))] })] }));
}

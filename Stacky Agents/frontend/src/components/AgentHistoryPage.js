import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Agents, Executions, Tickets, Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentHistoryPage.module.css";
// ── Helpers ────────────────────────────────────────────────────────────────
const AGENT_TYPE_BADGE = {
    business: { color: "#a371f7", bg: "rgba(163,113,247,0.18)", label: "Business" },
    functional: { color: "#f78166", bg: "rgba(247,129,102,0.18)", label: "Functional" },
    technical: { color: "#388bfd", bg: "rgba(56,139,253,0.18)", label: "Technical" },
    developer: { color: "#3fb950", bg: "rgba(63,185,80,0.18)", label: "Developer" },
    qa: { color: "#d29922", bg: "rgba(210,153,34,0.18)", label: "QA" },
    custom: { color: "#8b949e", bg: "rgba(139,148,158,0.18)", label: "Custom" },
};
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
function agentBadgeInfo(agentLabel) {
    const type = inferAgentType(agentLabel);
    const spec = AGENT_TYPE_BADGE[type] ?? AGENT_TYPE_BADGE.custom;
    return { style: { color: spec.color, backgroundColor: spec.bg }, label: spec.label };
}
function agentForFile(name, map) {
    const upper = name.toUpperCase();
    for (const [prefix, agent] of Object.entries(map)) {
        if (upper.startsWith(prefix.toUpperCase()))
            return agent;
    }
    return null;
}
function fmtDate(iso) {
    if (!iso)
        return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime()))
        return iso;
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" })
        + " " + d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}
function fmtDuration(ms) {
    if (!ms)
        return "";
    if (ms < 1000)
        return `${ms}ms`;
    const s = Math.round(ms / 1000);
    if (s < 60)
        return `${s}s`;
    return `${Math.floor(s / 60)}m ${s % 60}s`;
}
function statusLabel(s) {
    const map = {
        completed: "Completado",
        published: "Publicado",
        cancelled: "Cancelado",
        error: "Error",
        running: "En curso",
        pending: "Pendiente",
        vscode_chat: "VS Code Chat",
    };
    return map[s] ?? s;
}
function triggerDownload(filename, content) {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
}
function FileDetail({ ticketId, att, mode: initialMode, onClose, onDeleted }) {
    const [content, setContent] = useState("");
    const [editContent, setEditContent] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [mode, setMode] = useState(initialMode);
    const [rawView, setRawView] = useState(false);
    const ext = att.name.split(".").pop()?.toLowerCase() ?? "";
    const isMarkdown = ext === "md";
    const CODE_LANG = { sql: "sql", diff: "diff", patch: "diff" };
    const codeLang = CODE_LANG[ext] ?? "";
    const isRenderable = isMarkdown || !!codeLang;
    useEffect(() => {
        setLoading(true);
        setError(null);
        Tickets.attachmentContent(ticketId, att.url, att.name)
            .then((r) => {
            if (r.ok && r.content != null) {
                setContent(r.content);
                setEditContent(r.content);
            }
            else {
                setError(r.error ?? "No se pudo cargar el contenido");
            }
        })
            .catch((e) => setError(String(e)))
            .finally(() => setLoading(false));
    }, [ticketId, att.url, att.name]);
    const handleSave = useCallback(async () => {
        setSaving(true);
        setError(null);
        try {
            await Tickets.deleteAttachments(ticketId, [{ id: att.id, url: att.url, name: att.name }]);
            const res = await Tickets.uploadAttachment(ticketId, att.name, editContent);
            if (!res.ok) {
                setError(res.error ?? "Error al guardar");
                return;
            }
            onClose();
        }
        catch (e) {
            setError(String(e));
        }
        finally {
            setSaving(false);
        }
    }, [ticketId, att, editContent, onClose]);
    void onDeleted; // satisface el linter -- se propaga via onClose en el flujo de borrado del padre
    return (_jsxs("div", { className: styles.fileDetail, children: [_jsxs("div", { className: styles.fileDetailHeader, children: [_jsx("span", { className: styles.fileDetailName, children: att.name }), _jsxs("div", { className: styles.fileDetailActions, children: [mode === "view" && !loading && !error && (_jsxs(_Fragment, { children: [isRenderable && (_jsx("button", { className: styles.btnIcon, title: rawView ? "Ver renderizado" : "Ver raw", onClick: () => setRawView((v) => !v), children: rawView ? "Render" : "</>" })), _jsx("button", { className: styles.btnIcon, title: "Editar", onClick: () => setMode("edit"), children: "Editar" }), _jsx("button", { className: styles.btnIcon, title: "Descargar", onClick: () => triggerDownload(att.name, content), children: "Descargar" })] })), mode === "edit" && (_jsx("button", { className: styles.btnPrimary, onClick: handleSave, disabled: saving || loading, children: saving ? "Guardando..." : "Guardar" })), _jsx("button", { className: styles.btnClose, onClick: onClose, children: "X" })] })] }), error && _jsx("div", { className: styles.error, children: error }), loading ? (_jsx("div", { className: styles.loading, children: "Cargando..." })) : mode === "view" ? (isMarkdown && !rawView ? (_jsx("div", { className: styles.fileMarkdown, children: _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeHighlight], children: content }) })) : codeLang && !rawView ? (_jsx("div", { className: styles.fileMarkdown, children: _jsx(ReactMarkdown, { rehypePlugins: [rehypeHighlight], children: `\`\`\`${codeLang}\n${content}\n\`\`\`` }) })) : (_jsx("pre", { className: styles.fileContent, children: content }))) : (_jsx("textarea", { className: styles.fileEditor, value: editContent, onChange: (e) => setEditContent(e.target.value), spellCheck: false, disabled: saving }))] }));
}
function FilesTab({ ticketId, prefixAgentMap = {} }) {
    const [attachments, setAttachments] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [detail, setDetail] = useState(null);
    const [deleting, setDeleting] = useState(null);
    const [downloadingId, setDownloadingId] = useState(null);
    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        Tickets.attachments(ticketId)
            .then((r) => {
            setAttachments(r.attachments ?? []);
            if (r.error)
                setError(r.error);
        })
            .catch((e) => setError(String(e)))
            .finally(() => setLoading(false));
    }, [ticketId]);
    useEffect(() => { load(); }, [load]);
    const handleDelete = useCallback(async (att) => {
        if (!confirm(`Eliminar "${att.name}"?`))
            return;
        setDeleting(att.id);
        try {
            await Tickets.deleteAttachments(ticketId, [{ id: att.id, url: att.url, name: att.name }]);
            setAttachments((prev) => prev.filter((a) => a.id !== att.id));
            if (detail?.att.id === att.id)
                setDetail(null);
        }
        catch (e) {
            alert(String(e));
        }
        finally {
            setDeleting(null);
        }
    }, [ticketId, detail]);
    const handleDownload = useCallback(async (att) => {
        setDownloadingId(att.id);
        try {
            const r = await Tickets.attachmentContent(ticketId, att.url, att.name);
            if (r.ok && r.content != null) {
                triggerDownload(att.name, r.content);
            }
            else {
                alert(r.error ?? "No se pudo descargar");
            }
        }
        catch (e) {
            alert(String(e));
        }
        finally {
            setDownloadingId(null);
        }
    }, [ticketId]);
    if (loading)
        return _jsx("div", { className: styles.loading, children: "Cargando ficheros..." });
    if (error)
        return _jsx("div", { className: styles.error, children: error });
    if (detail) {
        return (_jsx(FileDetail, { ticketId: ticketId, att: detail.att, mode: detail.mode, onClose: () => { setDetail(null); load(); }, onDeleted: () => { setDetail(null); load(); } }));
    }
    if (!attachments.length) {
        return (_jsx("div", { className: styles.empty, children: "No hay ficheros adjuntos en este ticket." }));
    }
    return (_jsx("div", { className: styles.fileList, children: attachments.map((att) => {
            const agentLabel = agentForFile(att.name, prefixAgentMap);
            const badgeInfo = agentLabel ? agentBadgeInfo(agentLabel) : null;
            return (_jsxs("div", { className: styles.fileRow, children: [_jsx("span", { className: styles.fileIcon, children: "F" }), _jsx("span", { className: styles.fileName, children: att.name }), badgeInfo && (_jsx("span", { className: styles.agentBadge, style: badgeInfo.style, title: `Generado por: ${agentLabel}`, children: badgeInfo.label })), att.size > 0 && (_jsx("span", { className: styles.fileSize, children: att.size < 1024 ? `${att.size}B` : `${(att.size / 1024).toFixed(1)}KB` })), _jsxs("div", { className: styles.fileRowActions, children: [_jsx("button", { className: styles.btnIcon, title: "Ver", onClick: () => setDetail({ att, mode: "view" }), children: "Ver" }), _jsx("button", { className: styles.btnIcon, title: "Descargar", onClick: () => handleDownload(att), disabled: downloadingId === att.id, children: downloadingId === att.id ? "..." : "Bajar" }), _jsx("button", { className: styles.btnIcon, title: "Editar", onClick: () => setDetail({ att, mode: "edit" }), children: "Ed." }), _jsx("button", { className: `${styles.btnIcon} ${styles.btnDanger}`, title: "Eliminar", onClick: () => handleDelete(att), disabled: deleting === att.id, children: deleting === att.id ? "..." : "Elim." })] })] }, att.id));
        }) }));
}
function NotesTab({ ticketId, agentFilename, onAllDeleted }) {
    const [executions, setExecutions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [expanded, setExpanded] = useState(new Set());
    const [deleting, setDeleting] = useState(null);
    useEffect(() => {
        setLoading(true);
        setError(null);
        Executions.list({
            ticket_id: ticketId,
            agent_filename: agentFilename,
            include_output: true,
            limit: 100,
        })
            .then(setExecutions)
            .catch((e) => setError(String(e)))
            .finally(() => setLoading(false));
    }, [ticketId, agentFilename]);
    const toggle = (id) => setExpanded((prev) => {
        const next = new Set(prev);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
    });
    const handleDeleteNote = useCallback(async (ex) => {
        if (!confirm(`Eliminar esta ejecucion (#${ex.id})?`))
            return;
        setDeleting(ex.id);
        try {
            await Executions.deleteOne(ex.id);
            const remaining = executions.filter((e) => e.id !== ex.id);
            setExecutions(remaining);
            if (remaining.length === 0)
                onAllDeleted?.();
        }
        catch (e) {
            alert(String(e));
        }
        finally {
            setDeleting(null);
        }
    }, [executions, onAllDeleted]);
    if (loading)
        return _jsx("div", { className: styles.loading, children: "Cargando notas..." });
    if (error)
        return _jsx("div", { className: styles.error, children: error });
    if (!executions.length)
        return _jsx("div", { className: styles.empty, children: "No hay ejecuciones registradas para este ticket." });
    return (_jsx("div", { className: styles.notesList, children: executions.map((ex) => {
            const isExpanded = expanded.has(ex.id);
            const hasOutput = !!ex.output?.trim();
            const isDeletable = !["running", "queued", "vscode_chat"].includes(ex.status);
            return (_jsxs("div", { className: styles.noteCard, children: [_jsxs("div", { className: styles.noteHeader, onClick: () => hasOutput && toggle(ex.id), style: { cursor: hasOutput ? "pointer" : "default" }, children: [_jsx("span", { className: `${styles.statusBadge} ${styles[`status_${ex.status}`] ?? ""}`, children: statusLabel(ex.status) }), _jsx("span", { className: styles.noteDate, children: fmtDate(ex.started_at) }), ex.duration_ms != null && (_jsx("span", { className: styles.noteDuration, children: fmtDuration(ex.duration_ms) })), ex.agent_filename && (_jsx("span", { className: styles.noteAgent, children: ex.agent_filename })), hasOutput && (_jsx("span", { className: styles.noteToggle, children: isExpanded ? "v" : ">" })), isDeletable && (_jsx("button", { className: `${styles.btnIcon} ${styles.btnDanger}`, title: "Eliminar esta nota", onClick: (e) => { e.stopPropagation(); handleDeleteNote(ex); }, disabled: deleting === ex.id, style: { marginLeft: "auto" }, children: deleting === ex.id ? "..." : "Elim." }))] }), isExpanded && hasOutput && (_jsx("div", { className: styles.noteOutput, children: _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], children: ex.output }) })), ex.error_message && (_jsx("div", { className: styles.noteError, children: ex.error_message }))] }, ex.id));
        }) }));
}
// ── Main page ─────────────────────────────────────────────────────────────
export default function AgentHistoryPage({ filename, displayName, avatarValue, onBack, }) {
    const [tickets, setTickets] = useState([]);
    const [loadingTickets, setLoadingTickets] = useState(true);
    const [selectedId, setSelectedId] = useState(null);
    const [search, setSearch] = useState("");
    const [tab, setTab] = useState("notes");
    const [workflow, setWorkflow] = useState(null);
    const [forcing, setForcing] = useState(false);
    const [forceResult, setForceResult] = useState(null);
    const [reattaching, setReattaching] = useState(false);
    const [reattachResult, setReattachResult] = useState(null);
    const [deletingTicketId, setDeletingTicketId] = useState(null);
    const activeProject = useWorkbench((s) => s.activeProject);
    const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
    const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
    const prefixAgentMap = useMemo(() => {
        const map = {};
        for (const [fn, wf] of Object.entries(agentWorkflows)) {
            if (!wf.output_file_prefix)
                continue;
            const label = fn.replace(/\.agent\.md$/i, "").replace(/\.md$/i, "");
            for (const raw of (wf.output_file_prefix ?? "").split(",")) {
                const p = raw.trim();
                if (p)
                    map[p] = label;
            }
        }
        return map;
    }, [agentWorkflows]);
    // Cargar TODOS los workflows del proyecto para poder mapear ficheros => agente
    useEffect(() => {
        if (!activeProject?.name)
            return;
        Projects.getAllAgentWorkflows(activeProject.name)
            .then((r) => {
            if (r.ok && r.workflows) {
                setAgentWorkflows({ ...agentWorkflows, ...r.workflows });
            }
        })
            .catch(() => { });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeProject?.name]);
    // Cargar lista de tickets
    useEffect(() => {
        setLoadingTickets(true);
        Agents.history(filename, 100, activeProject?.name)
            .then((r) => {
            setTickets(r.tickets ?? []);
            if (r.tickets?.length)
                setSelectedId(r.tickets[0].ticket_id);
        })
            .catch(() => setTickets([]))
            .finally(() => setLoadingTickets(false));
    }, [filename, activeProject?.name]);
    // Cargar workflow config para force-transition
    useEffect(() => {
        const wf = agentWorkflows[filename];
        if (wf) {
            setWorkflow({ allowed_states: wf.allowed_states ?? [], transition_state: wf.transition_state ?? "" });
            return;
        }
        if (activeProject?.name) {
            Projects.getAgentWorkflow(activeProject.name, filename)
                .then((r) => {
                if (r.ok)
                    setWorkflow({ allowed_states: r.allowed_states ?? [], transition_state: r.transition_state ?? "" });
            })
                .catch(() => { });
        }
    }, [filename, agentWorkflows, activeProject]);
    const selectedTicket = tickets.find((t) => t.ticket_id === selectedId) ?? null;
    const filteredTickets = tickets.filter((t) => {
        if (!search.trim())
            return true;
        const q = search.trim().toLowerCase();
        return t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q);
    });
    const canForce = !!(workflow &&
        selectedTicket?.ado_state &&
        workflow.allowed_states.includes(selectedTicket.ado_state) &&
        selectedTicket.executions_count > 0 &&
        selectedTicket.last_execution_status === "completed");
    async function handleForce() {
        if (!selectedTicket)
            return;
        setForcing(true);
        setForceResult(null);
        try {
            const res = await Executions.forceTransition(selectedTicket.last_execution_id);
            setForceResult(res.ok ? `Transicionado a '${workflow?.transition_state}'` : (res.error ?? "Error al forzar transicion"));
        }
        catch (e) {
            setForceResult(String(e instanceof Error ? e.message : e));
        }
        finally {
            setForcing(false);
        }
    }
    async function handleReattach() {
        if (!selectedTicket)
            return;
        setReattaching(true);
        setReattachResult(null);
        try {
            const res = await Executions.reattach(selectedTicket.last_execution_id);
            setReattachResult(res.ok
                ? `Ficheros re-subidos (${res.tracker ?? ""} · prefijo: ${res.out_prefix ?? ""})`
                : (res.error ?? "Error al re-subir ficheros"));
        }
        catch (e) {
            setReattachResult(String(e instanceof Error ? e.message : e));
        }
        finally {
            setReattaching(false);
        }
    }
    async function handleDeleteTicket(t, e) {
        e.stopPropagation();
        if (!confirm(`Eliminar TODO el historial del ticket #${t.ado_id} "${t.title}"?\n\nSe borraran ${t.executions_count} ejecucion(es). Esta accion no se puede deshacer.`))
            return;
        setDeletingTicketId(t.ticket_id);
        try {
            await Executions.deleteByTicket(t.ticket_id, filename);
            const remaining = tickets.filter((tk) => tk.ticket_id !== t.ticket_id);
            setTickets(remaining);
            if (selectedId === t.ticket_id) {
                setSelectedId(remaining.length > 0 ? remaining[0].ticket_id : null);
            }
        }
        catch (err) {
            alert(String(err instanceof Error ? err.message : err));
        }
        finally {
            setDeletingTicketId(null);
        }
    }
    return (_jsxs("div", { className: styles.page, children: [_jsxs("div", { className: styles.header, children: [_jsx("button", { className: styles.backBtn, onClick: onBack, children: "Volver" }), _jsxs("div", { className: styles.agentInfo, children: [_jsx(PixelAvatar, { value: avatarValue, size: "sm", name: displayName }), _jsx("span", { className: styles.agentName, children: displayName })] }), _jsx("span", { className: styles.pageTitle, children: "Historial de ejecuciones" })] }), _jsxs("div", { className: styles.body, children: [_jsxs("aside", { className: styles.sidebar, children: [_jsxs("div", { className: styles.sidebarTitle, children: ["Tickets trabajados", activeProject ? ` · ${activeProject.display_name || activeProject.name}` : ""] }), _jsx("div", { className: styles.sidebarSearch, children: _jsx("input", { className: styles.sidebarSearchInput, type: "search", placeholder: "Buscar por titulo o ID...", value: search, onChange: (e) => setSearch(e.target.value) }) }), loadingTickets ? (_jsx("div", { className: styles.loading, children: "Cargando..." })) : filteredTickets.length === 0 ? (_jsx("div", { className: styles.sidebarEmpty, children: tickets.length === 0 ? "Sin historial" : "Sin resultados" })) : (_jsx("ul", { className: styles.ticketList, children: filteredTickets.map((t) => (_jsxs("li", { className: `${styles.ticketItem} ${selectedId === t.ticket_id ? styles.ticketItemActive : ""}`, onClick: () => { setSelectedId(t.ticket_id); setTab("notes"); setForceResult(null); setReattachResult(null); }, children: [_jsxs("div", { className: styles.ticketItemId, children: ["#", t.ado_id] }), _jsx("div", { className: styles.ticketItemTitle, children: t.title }), _jsxs("div", { className: styles.ticketItemMeta, children: [_jsxs("span", { className: styles.ticketItemCount, children: [t.executions_count, " ej."] }), t.ado_state && (_jsx("span", { className: styles.ticketItemState, children: t.ado_state })), _jsx("button", { className: `${styles.btnIcon} ${styles.btnDanger} ${styles.ticketDeleteBtn}`, title: "Eliminar historial completo de este ticket", onClick: (e) => handleDeleteTicket(t, e), disabled: deletingTicketId === t.ticket_id, children: deletingTicketId === t.ticket_id ? "..." : "Elim." })] })] }, t.ticket_id))) }))] }), _jsx("main", { className: styles.detail, children: !selectedTicket ? (_jsx("div", { className: styles.noSelection, children: "Selecciona un ticket para ver su historial." })) : (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.detailHeader, children: [_jsxs("div", { className: styles.detailTitle, children: [_jsxs("span", { className: styles.detailId, children: ["#", selectedTicket.ado_id] }), selectedTicket.title] }), selectedTicket.ado_url && (_jsx("a", { href: selectedTicket.ado_url, target: "_blank", rel: "noopener noreferrer", className: styles.detailLink, children: "Abrir" })), canForce && (_jsx("button", { className: styles.forceTransBtn, onClick: handleForce, disabled: forcing, title: `Transicionar a '${workflow?.transition_state}'`, children: forcing ? "..." : `=> ${workflow?.transition_state}` })), forceResult && (_jsx("span", { className: `${styles.forceResult} ${forceResult.startsWith("Transicion") ? styles.forceOk : styles.forceErr}`, children: forceResult })), selectedTicket.last_execution_status === "completed" && (_jsx("button", { className: styles.forceTransBtn, onClick: handleReattach, disabled: reattaching, title: "Re-intentar subir los ficheros generados al tracker", children: reattaching ? "..." : "Re-subir ficheros" })), reattachResult && (_jsx("span", { className: `${styles.forceResult} ${reattachResult.startsWith("Ficheros") ? styles.forceOk : styles.forceErr}`, children: reattachResult }))] }), _jsxs("div", { className: styles.tabs, children: [_jsx("button", { className: `${styles.tab} ${tab === "notes" ? styles.tabActive : ""}`, onClick: () => setTab("notes"), children: "Notas" }), _jsx("button", { className: `${styles.tab} ${tab === "files" ? styles.tabActive : ""}`, onClick: () => setTab("files"), children: "Ficheros" })] }), _jsxs("div", { className: styles.tabContent, children: [tab === "notes" && (_jsx(NotesTab, { ticketId: selectedTicket.ticket_id, agentFilename: filename, onAllDeleted: () => {
                                                const remaining = tickets.filter((tk) => tk.ticket_id !== selectedTicket.ticket_id);
                                                setTickets(remaining);
                                                setSelectedId(remaining.length > 0 ? remaining[0].ticket_id : null);
                                            } }, selectedTicket.ticket_id)), tab === "files" && (_jsx(FilesTab, { ticketId: selectedTicket.ticket_id, prefixAgentMap: prefixAgentMap }, selectedTicket.ticket_id))] })] })) })] })] }));
}

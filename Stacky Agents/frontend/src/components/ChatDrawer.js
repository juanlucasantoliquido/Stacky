import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * ChatDrawer – drawer deslizante para ejecuciones de agentes y chat libre.
 *
 * Fase 1 (setup): Selector de agente + modelo + ticket + botón Lanzar.
 * Fase 2 (chat):  Burbuja de prompt, streaming de respuesta, preguntas
 *                 interactivas y mensajes de seguimiento libres.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
const DOC_AGENT = "DocConsultor.agent.md";
import { useQuery } from "@tanstack/react-query";
import { AgentRoles, Agents, Chat, DocsRag, Projects, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./ChatDrawer.module.css";
// ── Helper ───────────────────────────────────────────────────────────────────
let _bubbleCounter = 0;
function nextId() { return `b${++_bubbleCounter}`; }
// ── ChatDrawer ───────────────────────────────────────────────────────────────
export default function ChatDrawer() {
    const { chatDrawerOpen, chatDrawerModel, chatDrawerTicketId, setChatDrawerOpen, activeProject, 
    // WS1 usa agentRuntime; lo exponemos como "runtime" para compatibilidad WS2
    agentRuntime: runtime, } = useWorkbench();
    // ── Proyecto anterior para detectar cambio ────────────────────────────────
    const prevProjectRef = useRef(undefined);
    // ── Setup state ────────────────────────────────────────────────────────────
    const [selectedAgent, setSelectedAgent] = useState("");
    const [selectedModel, setSelectedModel] = useState("");
    const [ticketQuery, setTicketQuery] = useState("");
    const [tickets, setTickets] = useState([]);
    const [filteredTickets, setFilteredTickets] = useState([]);
    const [selectedTicket, setSelectedTicket] = useState(null);
    // ── Workspace root for tool_executor file writes ─────────────────────────
    const [workspaceDir, setWorkspaceDir] = useState(null);
    // ── Chat state ─────────────────────────────────────────────────────────────
    const [phase, setPhase] = useState("setup");
    const [firstTurnDone, setFirstTurnDone] = useState(false);
    const [bubbles, setBubbles] = useState([]);
    const [history, setHistory] = useState([]);
    const [userInput, setUserInput] = useState("");
    const [sending, setSending] = useState(false);
    const [launching, setLaunching] = useState(false);
    const [launchError, setLaunchError] = useState(null);
    const [chatError, setChatError] = useState(null);
    const [indexing, setIndexing] = useState(false);
    const [indexMsg, setIndexMsg] = useState(null);
    const [exportFeedback, setExportFeedback] = useState(false);
    const chatBottomRef = useRef(null);
    const textareaRef = useRef(null);
    // ── Queries ────────────────────────────────────────────────────────────────
    const { data: agentsData } = useQuery({
        queryKey: ["vsCodeAgents"],
        queryFn: Agents.vsCodeAgents,
        staleTime: 60_000,
    });
    const { data: modelsData } = useQuery({
        queryKey: ["models"],
        queryFn: () => Agents.models(),
        staleTime: 60_000,
    });
    const agentsList = agentsData ?? [];
    const modelsList = modelsData?.models ?? [];
    // ── Agent roles (utilitario = visible en chat drawer) ─────────────────────
    const { data: rolesData } = useQuery({
        queryKey: ["agentRoles"],
        queryFn: AgentRoles.list,
        staleTime: 60_000,
    });
    const toolAgents = Object.entries(rolesData?.roles ?? {})
        .filter(([, r]) => r.utilitario)
        .map(([filename, r]) => ({ filename, label: r.name || filename, description: r.description }));
    // Inicializar selectedAgent al primer agente utilitario cuando cargan
    useEffect(() => {
        if (toolAgents.length > 0 && !selectedAgent) {
            const preferred = toolAgents.find((a) => a.filename === DOC_AGENT);
            setSelectedAgent(preferred?.filename ?? toolAgents[0].filename);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [toolAgents.length]);
    // ── Reset chat cuando cambia el proyecto ────────────────────────────────────
    useEffect(() => {
        const current = activeProject?.name;
        if (prevProjectRef.current !== undefined && prevProjectRef.current !== current) {
            setPhase("setup");
            setBubbles([]);
            setHistory([]);
            setFirstTurnDone(false);
            setChatError(null);
            setLaunchError(null);
            setSelectedTicket(null);
            setIndexMsg(null);
        }
        prevProjectRef.current = current;
    }, [activeProject?.name]);
    // ── Reset chat cuando cambia el agente ───────────────────────────────────
    const prevAgentRef = useRef("");
    useEffect(() => {
        if (prevAgentRef.current !== selectedAgent) {
            setPhase("setup");
            setBubbles([]);
            setHistory([]);
            setFirstTurnDone(false);
            setChatError(null);
            setLaunchError(null);
            setIndexMsg(null);
        }
        prevAgentRef.current = selectedAgent;
    }, [selectedAgent]);
    // ── Al abrir el drawer: obtener workspace_root (sin resetear chat activo) ───
    useEffect(() => {
        if (!chatDrawerOpen)
            return;
        if (chatDrawerModel)
            setSelectedModel(chatDrawerModel);
        Projects.agentBootstrap()
            .then((r) => { if (r.workspace_root)
            setWorkspaceDir(r.workspace_root); })
            .catch(() => { });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chatDrawerOpen]);
    // ── Load tickets when agent / project changes ──────────────────────────────
    useEffect(() => {
        if (!chatDrawerOpen || !selectedAgent)
            return;
        // WS1: Tickets.list solo acepta project (sin agent_filename)
        Tickets.list(activeProject?.name ?? undefined)
            .then((t) => {
            setTickets(t);
            setFilteredTickets(t.slice(0, 20));
            // Auto-select ticket pre-seleccionado desde AgentLaunchModal
            if (chatDrawerTicketId) {
                const match = t.find((ticket) => ticket.id === chatDrawerTicketId);
                if (match)
                    setSelectedTicket(match);
            }
        })
            .catch(() => { });
    }, [chatDrawerOpen, selectedAgent, activeProject?.name]);
    // ── Ticket filter ──────────────────────────────────────────────────────────
    useEffect(() => {
        const q = ticketQuery.toLowerCase().trim();
        if (!q) {
            setFilteredTickets(tickets.slice(0, 20));
            return;
        }
        setFilteredTickets(tickets
            .filter((t) => t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q))
            .slice(0, 20));
    }, [ticketQuery, tickets]);
    // ── Auto-scroll ────────────────────────────────────────────────────────────
    useEffect(() => {
        chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [bubbles]);
    // ── Indexar documentación (solo modo DocConsultor) ─────────────────────
    const isDocMode = selectedAgent === "DocConsultor.agent.md";
    async function handleIndexDocs() {
        setIndexing(true);
        setIndexMsg(null);
        try {
            const res = await DocsRag.index({ project_name: activeProject?.name });
            if (res.ok) {
                setIndexMsg(`✓ ${res.chunks_indexed} fragmentos indexados de ${res.files_scanned} ficheros.${res.warning ? " ⚠ " + res.warning : ""}`);
            }
            else {
                setIndexMsg(`✗ Error: ${res.error ?? "desconocido"}`);
            }
        }
        catch (err) {
            setIndexMsg(`✗ ${err instanceof Error ? err.message : String(err)}`);
        }
        finally {
            setIndexing(false);
        }
    }
    // ── Launch first turn via Chat.turn() ────────────────────────────────────
    async function handleLaunch() {
        if (!selectedAgent)
            return;
        setLaunchError(null);
        // Modo DocConsultor o sin ticket: saltar directamente al chat libre
        if (isDocMode || !selectedTicket) {
            setHistory([]);
            setBubbles([]);
            setPhase("chat");
            setFirstTurnDone(true);
            setTimeout(() => textareaRef.current?.focus(), 50);
            return;
        }
        setLaunching(true);
        setFirstTurnDone(false);
        const userCtx = `Ticket #${selectedTicket.ado_id}: ${selectedTicket.title}`
            + (selectedTicket.description ? `\n\n${selectedTicket.description}` : "");
        const userBubble = {
            id: nextId(),
            kind: "user",
            text: `#${selectedTicket.ado_id}: ${selectedTicket.title}`,
        };
        const waitingBubble = { id: nextId(), kind: "assistant", text: "", streaming: true };
        const initMessages = [{ role: "user", content: userCtx }];
        setHistory(initMessages);
        setBubbles([userBubble, waitingBubble]);
        setPhase("chat");
        try {
            const res = await Chat.turn({
                agent_filename: selectedAgent,
                model: selectedModel || null,
                messages: initMessages,
                workspace_dir: workspaceDir,
                runtime,
                project_name: activeProject?.name ?? null,
            });
            const assistantText = res.text ?? "";
            const finalHistory = [
                ...initMessages,
                { role: "assistant", content: assistantText },
            ];
            setHistory(finalHistory);
            setBubbles([userBubble, { ...waitingBubble, text: assistantText, streaming: false, toolLog: res.tool_log }]);
            setFirstTurnDone(true);
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setLaunchError(msg);
            setPhase("setup");
            setBubbles([]);
            setHistory([]);
        }
        finally {
            setLaunching(false);
            setTimeout(() => textareaRef.current?.focus(), 50);
        }
    }
    // ── Send free-turn message ─────────────────────────────────────────────────
    const sendMessage = useCallback(async () => {
        const text = userInput.trim();
        if (!text || sending || !selectedAgent)
            return;
        setSending(true);
        setChatError(null);
        const userBubble = { id: nextId(), kind: "user", text };
        const streamingBubble = { id: nextId(), kind: "assistant", text: "", streaming: true };
        setBubbles((prev) => [...prev, userBubble, streamingBubble]);
        setUserInput("");
        const updatedHistory = [
            ...history,
            { role: "user", content: text },
        ];
        setHistory(updatedHistory);
        try {
            let assistantText = "";
            let toolLog;
            let ragSources;
            if (isDocMode) {
                const res = await DocsRag.chat({
                    messages: updatedHistory,
                    agent_filename: selectedAgent,
                    model: selectedModel || null,
                    workspace_dir: workspaceDir,
                });
                assistantText = res.text ?? "";
                ragSources = res.sources?.length ? res.sources : undefined;
            }
            else {
                const res = await Chat.turn({
                    agent_filename: selectedAgent,
                    model: selectedModel || null,
                    messages: updatedHistory,
                    workspace_dir: workspaceDir,
                    runtime,
                    project_name: activeProject?.name ?? null,
                });
                assistantText = res.text ?? "";
                toolLog = res.tool_log;
            }
            const finalHistory = [
                ...updatedHistory,
                { role: "assistant", content: assistantText },
            ];
            setHistory(finalHistory);
            setBubbles((prev) => prev.map((b) => b.id === streamingBubble.id
                ? { ...b, text: assistantText, streaming: false, toolLog, sources: ragSources }
                : b));
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setChatError(msg);
            setBubbles((prev) => prev.filter((b) => b.id !== streamingBubble.id));
        }
        finally {
            setSending(false);
            setTimeout(() => textareaRef.current?.focus(), 50);
        }
    }, [userInput, sending, selectedAgent, selectedModel, history]);
    // textarea Enter to send (Shift+Enter = newline)
    function handleKeyDown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }
    // Copy text to clipboard
    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
        }
        catch { /* noop */ }
    }
    // Reset back to setup
    function resetToSetup() {
        setPhase("setup");
        setFirstTurnDone(false);
        setBubbles([]);
        setHistory([]);
        setChatError(null);
        setSelectedTicket(null);
        setTicketQuery("");
    }
    // ── Export chat ────────────────────────────────────────────────────────────
    function handleExportChat() {
        const projectName = activeProject?.name ?? "Proyecto";
        const dateStr = new Date().toLocaleString("es-ES", {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
        const lines = [
            `# Chat DocConsultor — ${projectName}`,
            `*${dateStr}*`,
            ``,
        ];
        for (const b of bubbles) {
            if (b.kind === "user") {
                lines.push(`---`, ``);
                lines.push(`**Yo:** ${b.text}`, ``);
            }
            else if (b.kind === "assistant" && b.text) {
                lines.push(`**DocConsultor:**`, ``);
                lines.push(b.text, ``);
            }
        }
        const text = lines.join("\n");
        navigator.clipboard.writeText(text).then(() => {
            setExportFeedback(true);
            setTimeout(() => setExportFeedback(false), 2000);
        }).catch(() => { });
    }
    // ── Close ──────────────────────────────────────────────────────────────────
    function handleClose() {
        setChatDrawerOpen(false);
    }
    const canSendFreeMessage = phase === "chat" && firstTurnDone && !sending;
    const currentAgentMeta = toolAgents.find((a) => a.filename === selectedAgent) ?? toolAgents[0];
    const currentAgentName = agentsList.find((a) => a.filename === selectedAgent)?.name ??
        currentAgentMeta?.label ?? selectedAgent;
    return (_jsxs(_Fragment, { children: [chatDrawerOpen && _jsx("div", { className: styles.overlay, "aria-hidden": "true" }), _jsxs("aside", { className: `${styles.drawer}${!chatDrawerOpen ? " " + styles.drawerClosed : ""}`, role: "complementary", "aria-label": "Chat documental", children: [_jsxs("div", { className: styles.header, children: [_jsx("span", { className: styles.headerTitle, children: phase === "setup" ? "💬 Nuevo Chat" : `🤖 ${currentAgentName}` }), phase === "chat" && (_jsxs(_Fragment, { children: [_jsx("button", { className: styles.closeBtn, onClick: handleExportChat, title: "Exportar chat (copiar al portapapeles)", style: exportFeedback ? { color: "#86efac" } : undefined, children: exportFeedback ? "✓ Copiado" : "⬆ Exportar" }), _jsx("button", { className: styles.closeBtn, onClick: resetToSetup, title: "Nueva conversaci\u00F3n", children: "\u2726" })] })), _jsx("button", { className: styles.closeBtn, onClick: handleClose, title: "Cerrar", "aria-label": "Cerrar chat", children: "\u2715" })] }), phase === "setup" && (_jsxs("div", { className: styles.setup, children: [_jsxs("div", { className: styles.field, children: [_jsx("span", { className: styles.label, children: "Agente" }), _jsx("select", { className: styles.select, value: selectedAgent, onChange: (e) => setSelectedAgent(e.target.value), children: toolAgents.map((ag) => (_jsx("option", { value: ag.filename, title: ag.description, children: ag.label }, ag.filename))) })] }), _jsxs("div", { className: styles.field, children: [_jsx("span", { className: styles.label, children: "Modelo" }), modelsList.length > 0 ? (_jsxs("select", { className: styles.select, value: selectedModel, onChange: (e) => setSelectedModel(e.target.value), children: [_jsx("option", { value: "", children: "\u2014 Default \u2014" }), modelsList.map((m) => (_jsx("option", { value: m.id, children: m.name }, m.id)))] })) : (_jsx("input", { className: styles.input, value: selectedModel, onChange: (e) => setSelectedModel(e.target.value), placeholder: "ej: gpt-4o (dejar vac\u00EDo = default)" }))] }), isDocMode && (_jsxs("div", { className: styles.field, children: [_jsx("span", { className: styles.label, children: "Documentaci\u00F3n" }), _jsx("button", { className: styles.indexBtn, disabled: indexing, onClick: handleIndexDocs, children: indexing ? _jsx("span", { className: styles.spinner }) : "⟳ Indexar docs" }), indexMsg && (_jsx("div", { className: indexMsg.startsWith("✓") ? styles.indexMsgOk : styles.errorNotice, children: indexMsg }))] })), selectedAgent && !isDocMode && (_jsxs("div", { className: styles.field, children: [_jsx("span", { className: styles.label, children: "Ticket" }), _jsx("input", { className: styles.input, value: ticketQuery, onChange: (e) => setTicketQuery(e.target.value), placeholder: "Buscar por t\u00EDtulo o ID\u2026" }), filteredTickets.length > 0 && (_jsx("div", { className: styles.ticketList, children: filteredTickets.map((t) => (_jsxs("div", { className: `${styles.ticketItem} ${selectedTicket?.id === t.id ? styles.selected : ""}`, onClick: () => setSelectedTicket(t), children: [_jsxs("strong", { children: ["#", t.ado_id] }), " ", t.title] }, t.id))) })), selectedTicket && (_jsxs("div", { style: { fontSize: "0.75rem", color: "#a78bfa", marginTop: "0.25rem" }, children: ["\u2713 #", selectedTicket.ado_id, " ", selectedTicket.title] }))] })), launchError && (_jsx("div", { className: styles.errorNotice, children: launchError })), _jsx("button", { className: styles.launchBtn, disabled: !selectedAgent || launching, onClick: handleLaunch, children: launching ? _jsx("span", { className: styles.spinner }) : "▶ Lanzar" })] })), phase === "chat" && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.chatArea, children: [bubbles.map((b) => (_jsx(BubbleView, { bubble: b, onCopy: copyText, 
                                        // Pass question answer props only for active question
                                        isActiveQuestion: false, pendingAnswer: "", onAnswerChange: () => { }, onAnswerSubmit: () => { } }, b.id))), launching && phase === "chat" && (_jsxs("div", { className: `${styles.bubble} ${styles.system}`, children: ["Generando respuesta", _jsx("span", { className: styles.streamingDot })] })), chatError && (_jsx("div", { className: styles.errorNotice, children: chatError })), _jsx("div", { ref: chatBottomRef })] }), _jsx("div", { className: styles.footer, children: _jsxs("div", { className: styles.inputRow, children: [_jsx("textarea", { ref: textareaRef, className: styles.messageInput, value: userInput, onChange: (e) => setUserInput(e.target.value), onKeyDown: handleKeyDown, placeholder: canSendFreeMessage ? "Continuá la conversación…" : launching ? "Esperando respuesta…" : "Lanzá una ejecución primero…", disabled: !canSendFreeMessage, rows: 1 }), _jsx("button", { className: styles.sendBtn, disabled: !canSendFreeMessage || !userInput.trim(), onClick: sendMessage, title: "Enviar (Enter)", children: sending ? _jsx("span", { className: styles.spinner }) : "↑" })] }) })] }))] })] }));
}
function BubbleView({ bubble, onCopy, isActiveQuestion, pendingAnswer, onAnswerChange, onAnswerSubmit, }) {
    const cls = `${styles.bubble} ${styles[bubble.kind]}`;
    if (bubble.kind === "question") {
        return (_jsxs("div", { className: cls, children: [_jsxs("div", { children: ["\u2753 ", bubble.text] }), isActiveQuestion && (_jsxs("div", { className: styles.questionForm, children: [_jsx("input", { className: styles.questionInput, value: pendingAnswer, onChange: (e) => onAnswerChange(e.target.value), placeholder: "Tu respuesta\u2026", onKeyDown: (e) => { if (e.key === "Enter") {
                                e.preventDefault();
                                onAnswerSubmit();
                            } }, autoFocus: true }), _jsx("button", { className: styles.answerBtn, onClick: onAnswerSubmit, disabled: !pendingAnswer.trim(), children: "Enviar" })] }))] }));
    }
    if (bubble.kind === "assistant") {
        return (_jsxs("div", { className: cls, children: [_jsx("button", { className: styles.copyBtn, onClick: () => onCopy(bubble.text), title: "Copiar respuesta", children: "\u2398 copiar" }), _jsx("div", { className: styles.prose, children: _jsx(ReactMarkdown, { children: bubble.text }) }), bubble.streaming && _jsx("span", { className: styles.streamingDot }), bubble.toolLog && bubble.toolLog.length > 0 && (_jsx("div", { className: `${styles.bubble} ${styles.toolLog}`, style: { marginTop: "0.5rem" }, children: bubble.toolLog.map((t, i) => (_jsxs("div", { children: [_jsx("strong", { children: t.tool }), t.ok ? " ✓" : " ✗", " ", _jsx("span", { style: { opacity: 0.7 }, children: t.args })] }, i))) }))] }));
    }
    if (bubble.kind === "system") {
        return _jsx("div", { className: cls, children: bubble.text });
    }
    // user / toolLog
    return (_jsx("div", { className: cls, children: bubble.kind === "toolLog"
            ? _jsx("pre", { style: { margin: 0 }, children: bubble.text })
            : bubble.text }));
}

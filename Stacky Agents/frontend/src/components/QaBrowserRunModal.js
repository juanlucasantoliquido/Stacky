import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Copy, Play, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { QaBrowser, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./QaBrowserRunModal.module.css";
const DEFAULT_BASE_URL = "http://localhost:35017/AgendaWeb/";
export default function QaBrowserRunModal({ ticket, onClose }) {
    const [tickets, setTickets] = useState([]);
    const [query, setQuery] = useState("");
    const [selected, setSelected] = useState(ticket ?? null);
    const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem("stacky_qa_browser_base_url") || DEFAULT_BASE_URL);
    const [note, setNote] = useState("");
    const [loading, setLoading] = useState(false);
    const [copyState, setCopyState] = useState("idle");
    const [error, setError] = useState(null);
    const [run, setRun] = useState(null);
    const activeProjectName = useWorkbench((state) => state.activeProject?.name ?? null);
    const setCodexConsoleExecution = useWorkbench((state) => state.setCodexConsoleExecution);
    useEffect(() => {
        if (ticket)
            return;
        Tickets.list(activeProjectName).then(setTickets).catch(() => setTickets([]));
    }, [activeProjectName, ticket]);
    const filteredTickets = useMemo(() => {
        if (ticket)
            return [];
        const q = query.trim().toLowerCase();
        if (!q)
            return tickets.slice(0, 30);
        return tickets
            .filter((t) => String(t.ado_id).includes(q) ||
            t.title.toLowerCase().includes(q) ||
            (t.project ?? "").toLowerCase().includes(q))
            .slice(0, 30);
    }, [query, ticket, tickets]);
    async function copyPrompt(text) {
        try {
            await navigator.clipboard.writeText(text);
            setCopyState("copied");
        }
        catch {
            setCopyState("failed");
        }
    }
    async function handleStart() {
        if (!selected)
            return;
        setLoading(true);
        setError(null);
        try {
            localStorage.setItem("stacky_qa_browser_base_url", baseUrl);
            const response = await QaBrowser.startRun({
                ticket_id: selected.id,
                allowed_base_url: baseUrl,
                operator_note: note.trim() || undefined,
                max_scenarios: 16,
                auto_start: true,
            });
            setRun(response);
            setCodexConsoleExecution(response.execution_id, false);
            if (response.status === "queued") {
                await copyPrompt(response.runner_prompt);
            }
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setLoading(false);
        }
    }
    const selectedLabel = selected
        ? `ADO-${selected.ado_id} - ${selected.title}`
        : "Selecciona un ticket";
    const runStarted = run?.status === "running";
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => e.currentTarget === e.target && onClose(), children: _jsxs("section", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "TEST QA UAT CODEX", children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { children: [_jsx("h2", { children: "TEST QA UAT CODEX" }), _jsx("p", { children: selectedLabel })] }), _jsx("button", { className: styles.iconButton, onClick: onClose, title: "Cerrar", children: _jsx(X, { size: 16 }) })] }), !ticket && (_jsxs(_Fragment, { children: [_jsx("input", { className: styles.input, placeholder: "Buscar ticket por ID, titulo o proyecto", value: query, onChange: (e) => setQuery(e.target.value) }), _jsx("div", { className: styles.ticketList, children: filteredTickets.map((t) => (_jsxs("button", { className: selected?.id === t.id ? styles.ticketActive : styles.ticket, onClick: () => setSelected(t), children: [_jsxs("span", { children: ["ADO-", t.ado_id] }), _jsx("strong", { children: t.title }), _jsx("em", { children: t.ado_state ?? "-" })] }, t.id))) })] })), _jsxs("label", { className: styles.field, children: [_jsx("span", { children: "URL base permitida" }), _jsx("input", { className: styles.input, value: baseUrl, onChange: (e) => setBaseUrl(e.target.value), placeholder: DEFAULT_BASE_URL })] }), _jsxs("label", { className: styles.field, children: [_jsx("span", { children: "Nota para el tester" }), _jsx("textarea", { className: styles.textarea, value: note, onChange: (e) => setNote(e.target.value), placeholder: "Datos de prueba, usuario ya logueado, pantalla inicial esperada..." })] }), error && _jsx("div", { className: styles.error, children: error }), run && (_jsxs("div", { className: styles.result, children: [_jsxs("div", { className: styles.resultTop, children: [_jsxs("span", { children: ["Run #", run.execution_id] }), _jsx("span", { children: run.status === "queued" ? "preparado" : run.status }), _jsxs("span", { children: [run.spec.scenarios.length, " escenarios"] }), _jsxs("span", { children: [run.spec.plan_source.used_sources.length, " fuentes"] })] }), _jsxs("div", { className: styles.handoff, children: [_jsx("strong", { children: runStarted ? "Run iniciado." : "Run preparado." }), _jsx("span", { children: runStarted
                                        ? "Stacky ya trajo descripcion, comentarios y adjuntos del ticket, inicio Codex y abrio la consola para seguir la ejecucion. El prompt queda disponible abajo como respaldo operativo."
                                        : "Stacky ya trajo descripcion, comentarios y adjuntos del ticket. El prompt quedo copiado: pegalo en Codex para que el navegador visible ejecute el plan y cierre el run publicando el comentario en ADO." })] }), _jsx("div", { className: styles.sourceList, children: run.spec.plan_source.used_sources.length === 0 ? (_jsx("span", { children: "Sin fuente de plan detectable" })) : (run.spec.plan_source.used_sources.map((src) => (_jsx("span", { children: src.title }, `${src.kind}-${src.source_id}`)))) }), _jsx("textarea", { className: styles.prompt, readOnly: true, value: run.runner_prompt })] })), _jsxs("footer", { className: styles.actions, children: [run && (_jsxs("button", { className: styles.secondaryBtn, onClick: () => copyPrompt(run.runner_prompt), children: [_jsx(Copy, { size: 14 }), copyState === "copied" ? "Prompt copiado" : copyState === "failed" ? "No se pudo copiar" : "Copiar prompt"] })), _jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cerrar" }), _jsxs("button", { className: styles.primaryBtn, onClick: handleStart, disabled: !selected || loading, children: [_jsx(Play, { size: 14 }), loading ? "Preparando..." : "TEST QA UAT CODEX"] })] })] }) }));
}

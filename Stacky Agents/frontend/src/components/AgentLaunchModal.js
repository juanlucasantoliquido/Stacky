import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useRef } from "react";
import { Tickets } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentLaunchModal.module.css";
const BRIDGE_BASE = "http://localhost:5052";
export default function AgentLaunchModal({ agent, avatarValue, onClose }) {
    const [query, setQuery] = useState("");
    const [tickets, setTickets] = useState([]);
    const [filtered, setFiltered] = useState([]);
    const [selected, setSelected] = useState(null);
    const [comments, setComments] = useState([]);
    const [commentsLoading, setCommentsLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(false);
    const [bridgeError, setBridgeError] = useState(false);
    const [success, setSuccess] = useState(false);
    const searchRef = useRef(null);
    const debounceRef = useRef(null);
    // load tickets once
    useEffect(() => {
        Tickets.list().then((t) => {
            setTickets(t);
            setFiltered(t.slice(0, 20));
        }).catch(() => { });
        searchRef.current?.focus();
    }, []);
    // debounced filter
    useEffect(() => {
        if (debounceRef.current)
            clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            if (!query.trim()) {
                setFiltered(tickets.slice(0, 20));
            }
            else {
                const q = query.toLowerCase();
                setFiltered(tickets
                    .filter((t) => String(t.ado_id).includes(q) ||
                    t.title.toLowerCase().includes(q) ||
                    (t.project ?? "").toLowerCase().includes(q))
                    .slice(0, 20));
            }
        }, 200);
    }, [query, tickets]);
    // fetch comments when a ticket is selected
    useEffect(() => {
        if (!selected) {
            setComments([]);
            return;
        }
        setCommentsLoading(true);
        Tickets.comments(selected.id)
            .then((r) => setComments(r.comments ?? []))
            .catch(() => setComments([]))
            .finally(() => setCommentsLoading(false));
    }, [selected]);
    async function handleLaunch() {
        if (!selected)
            return;
        setLoading(true);
        setBridgeError(false);
        // Build full ticket context so Copilot Chat receives more than just the title
        const parts = [`#ADO-${selected.ado_id} ${selected.title}`];
        const metaParts = [];
        if (selected.ado_state)
            metaParts.push(`Estado: **${selected.ado_state}**`);
        if (selected.priority != null)
            metaParts.push(`Prioridad: **${selected.priority}**`);
        if (selected.ado_url)
            metaParts.push(`[Ver en Azure DevOps](${selected.ado_url})`);
        if (metaParts.length)
            parts.push(metaParts.join(" | "));
        if (selected.description?.trim()) {
            parts.push(`\n## Descripción del ticket\n${selected.description.trim()}`);
        }
        if (comments.length) {
            const notesBlock = comments
                .map((c) => `**${c.author}** (${c.date}):\n${c.text}`)
                .join("\n\n---\n\n");
            parts.push(`\n## Notas / Comentarios del ticket\n${notesBlock}`);
        }
        if (message)
            parts.push(`\n## Mensaje adicional\n${message}`);
        const chatMessage = parts.join("\n\n");
        try {
            const res = await fetch(`${BRIDGE_BASE}/open-chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    agent_name: agent.filename,
                    message: chatMessage,
                }),
            });
            if (!res.ok)
                throw new Error(`Bridge responded ${res.status}`);
            setSuccess(true);
            setTimeout(onClose, 1200);
        }
        catch {
            setBridgeError(true);
        }
        finally {
            setLoading(false);
        }
    }
    // close on backdrop click
    function handleBackdrop(e) {
        if (e.target === e.currentTarget)
            onClose();
    }
    const displayName = agent.name ?? agent.filename.replace(/\.agent\.md$/i, "");
    return (_jsx("div", { className: styles.backdrop, onClick: handleBackdrop, children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "Asignar ticket", children: [_jsxs("div", { className: styles.header, children: [_jsx(PixelAvatar, { value: avatarValue, size: "sm", name: displayName }), _jsxs("div", { className: styles.headerText, children: [_jsx("span", { className: styles.agentName, children: displayName }), _jsx("span", { className: styles.subtitle, children: "\u00BFQu\u00E9 ticket quer\u00E9s trabajar?" })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsx("div", { className: styles.searchWrap, children: _jsx("input", { ref: searchRef, className: styles.search, type: "text", placeholder: "Buscar por ID, t\u00EDtulo o proyecto\u2026", value: query, onChange: (e) => setQuery(e.target.value) }) }), _jsx("div", { className: styles.list, children: filtered.length === 0 ? (_jsx("div", { className: styles.empty, children: "No se encontraron tickets" })) : (filtered.map((t) => (_jsxs("button", { className: selected?.id === t.id ? styles.ticketActive : styles.ticket, onClick: () => setSelected(t), children: [_jsxs("span", { className: styles.ticketId, children: ["ADO-", t.ado_id] }), _jsx("span", { className: styles.ticketTitle, children: t.title }), t.ado_state && (_jsx("span", { className: styles.ticketState, children: t.ado_state }))] }, t.id)))) }), _jsx("textarea", { className: styles.messageInput, placeholder: "Mensaje inicial (opcional)\u2026", value: message, onChange: (e) => setMessage(e.target.value), rows: 2 }), bridgeError && (_jsx("div", { className: styles.error, children: "\u26A0\uFE0F La extensi\u00F3n VS Code no est\u00E1 activa. Abr\u00ED VS Code con la extensi\u00F3n Stacky para continuar." })), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cancelar" }), _jsx("button", { className: styles.launchBtn, onClick: handleLaunch, disabled: !selected || loading || success, children: success ? "✓ Abriendo…" : loading ? "Enviando…" : "OK — Abrir en VS Code Chat" })] })] }) }));
}

import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useRef } from "react";
import { Agents, Tickets } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentLaunchModal.module.css";
// Endpoint del bridge de la extensión VS Code (Stacky Agents).
// Solo lo usamos para el health-check informativo: la llamada real a /open-chat
// va por el backend Flask vía `Agents.openChat()`.
const BRIDGE_BASE = "http://localhost:5052";
/**
 * Health-check del bridge de la extensión VS Code.
 *
 * Pega a `GET http://localhost:5052/health` (CORS abierto en la extensión).
 * Devuelve `true` solo si el bridge responde 200 — diferenciamos esto
 * explícitamente del flujo de POST /open-chat para evitar falsos positivos
 * del banner "extensión no está activa" cuando el problema real es otro
 * (CORS, timeout puntual, payload mal armado, ticket inexistente, etc.).
 *
 * Timeout corto (1.5s) — si no responde rápido, asumimos que está caído.
 * No expone errores: cualquier fallo → false.
 */
async function checkBridgeHealth() {
    try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 1500);
        const res = await fetch(`${BRIDGE_BASE}/health`, {
            method: "GET",
            signal: ctrl.signal,
        });
        clearTimeout(t);
        return res.ok;
    }
    catch {
        return false;
    }
}
export default function AgentLaunchModal({ agent, avatarValue, onClose }) {
    const [query, setQuery] = useState("");
    const [tickets, setTickets] = useState([]);
    const [filtered, setFiltered] = useState([]);
    const [selected, setSelected] = useState(null);
    const [comments, setComments] = useState([]);
    const [commentsLoading, setCommentsLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(false);
    const [bridgeStatus, setBridgeStatus] = useState("unknown");
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);
    const searchRef = useRef(null);
    const debounceRef = useRef(null);
    // load tickets once + initial bridge health probe (informativo, no bloqueante)
    useEffect(() => {
        Tickets.list().then((t) => {
            setTickets(t);
            setFiltered(t.slice(0, 20));
        }).catch(() => { });
        searchRef.current?.focus();
        // Probe inicial del bridge — si está caído, mostramos un aviso suave
        // que NO bloquea seleccionar ticket ni escribir mensaje. El usuario puede
        // levantar VS Code mientras prepara la asignación.
        setBridgeStatus("checking");
        checkBridgeHealth().then((ok) => {
            setBridgeStatus(ok ? "ready" : "down");
        });
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
    /**
     * Re-chequea el bridge cuando el usuario hace clic en "Reintentar" del banner.
     * Cubre el caso típico: usuario levanta VS Code después de abrir el modal.
     */
    async function retryBridgeProbe() {
        setBridgeStatus("checking");
        const ok = await checkBridgeHealth();
        setBridgeStatus(ok ? "ready" : "down");
        if (ok)
            setError(null);
    }
    /**
     * Convierte un error del backend `/api/agents/open-chat` en un `BridgeError`
     * con un mensaje específico para el usuario. El backend devuelve HTTP
     * granulares: 503 (bridge caído), 504 (timeout), 502 (bridge respondió 5xx),
     * 400 (payload inválido), 404 (ticket no existe).
     */
    function mapBackendError(rawMessage) {
        const m = rawMessage || "";
        if (m.includes("503")) {
            return {
                kind: "extension_down",
                message: "La extensión VS Code no está activa. Abrí VS Code con la extensión Stacky y reintentá.",
                detail: m,
            };
        }
        if (m.includes("504")) {
            return {
                kind: "bridge_timeout",
                message: "VS Code recibió la solicitud pero tardó demasiado en responder. Reintentá en unos segundos.",
                detail: m,
            };
        }
        if (m.includes("502")) {
            return {
                kind: "bridge_error",
                message: "VS Code respondió con un error al abrir el chat. Revisá los logs de la extensión Stacky.",
                detail: m,
            };
        }
        if (m.includes("404")) {
            return {
                kind: "ticket_not_found",
                message: "El ticket seleccionado no se encontró en la base de Stacky. Probá sincronizar tickets primero.",
                detail: m,
            };
        }
        return {
            kind: "unknown",
            message: "No se pudo abrir el chat. Revisá la consola del backend para más detalle.",
            detail: m,
        };
    }
    async function handleLaunch() {
        if (!selected)
            return;
        setLoading(true);
        setError(null);
        try {
            // Routing correcto: vamos al backend Flask, NO directo al bridge.
            // El backend (`/api/agents/open-chat`) ya:
            //   1. Levanta el ticket de la DB con todos los metadatos
            //   2. Enriquece con comentarios + adjuntos de ADO
            //   3. Llama al bridge desde el server (sin CORS browser)
            //   4. Devuelve errores HTTP granulares (503/504/502)
            // El message adicional opcional se manda como un context_block libre
            // siguiendo el shape de `ContextBlock` (ver `frontend/src/types.ts`).
            const contextBlocks = message.trim()
                ? [
                    {
                        id: "modal_user_input",
                        kind: "editable",
                        title: "Mensaje adicional",
                        content: message.trim(),
                        source: { type: "modal_user_input" },
                    },
                ]
                : [];
            await Agents.openChat({
                ticket_id: selected.id,
                context_blocks: contextBlocks,
                vscode_agent_filename: agent.filename,
            });
            setSuccess(true);
            // Bridge respondió OK → confirmamos status para el banner
            setBridgeStatus("ready");
            setTimeout(onClose, 1200);
        }
        catch (e) {
            setError(mapBackendError(String(e)));
            // Si el backend dijo 503, también marcamos el bridge como down
            // para que el banner permanezco hasta el próximo retry.
            if (String(e).includes("503")) {
                setBridgeStatus("down");
            }
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
    return (_jsx("div", { className: styles.backdrop, onClick: handleBackdrop, children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "Asignar ticket", children: [_jsxs("div", { className: styles.header, children: [_jsx(PixelAvatar, { value: avatarValue, size: "sm", name: displayName }), _jsxs("div", { className: styles.headerText, children: [_jsx("span", { className: styles.agentName, children: displayName }), _jsx("span", { className: styles.subtitle, children: "\u00BFQu\u00E9 ticket quer\u00E9s trabajar?" })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), bridgeStatus === "down" && !error && (_jsxs("div", { className: styles.warning, role: "status", children: [_jsx("span", { children: "VS Code no est\u00E1 conectado al bridge de Stacky. Pod\u00E9s seleccionar el ticket; cuando abras VS Code reintent\u00E1." }), _jsx("button", { className: styles.retryBtn, onClick: retryBridgeProbe, type: "button", children: "Reintentar" })] })), _jsx("div", { className: styles.searchWrap, children: _jsx("input", { ref: searchRef, className: styles.search, type: "text", placeholder: "Buscar por ID, t\u00EDtulo o proyecto\u2026", value: query, onChange: (e) => setQuery(e.target.value) }) }), _jsx("div", { className: styles.list, children: filtered.length === 0 ? (_jsx("div", { className: styles.empty, children: "No se encontraron tickets" })) : (filtered.map((t) => (_jsxs("button", { className: selected?.id === t.id ? styles.ticketActive : styles.ticket, onClick: () => setSelected(t), children: [_jsxs("span", { className: styles.ticketId, children: ["ADO-", t.ado_id] }), _jsx("span", { className: styles.ticketTitle, children: t.title }), t.ado_state && (_jsx("span", { className: styles.ticketState, children: t.ado_state }))] }, t.id)))) }), _jsx("textarea", { className: styles.messageInput, placeholder: "Mensaje inicial (opcional)\u2026", value: message, onChange: (e) => setMessage(e.target.value), rows: 2 }), error && (_jsxs("div", { className: styles.error, role: "alert", children: [_jsxs("span", { children: ["\u26A0\uFE0F ", error.message] }), error.kind === "extension_down" && (_jsx("button", { className: styles.retryBtn, onClick: retryBridgeProbe, type: "button", children: "Reintentar conexi\u00F3n" })), error.detail && (_jsxs("details", { className: styles.errorDetail, children: [_jsx("summary", { children: "Detalle t\u00E9cnico" }), _jsx("pre", { children: error.detail })] }))] })), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cancelar" }), _jsx("button", { className: styles.launchBtn, onClick: handleLaunch, disabled: !selected || loading || success, children: success ? "✓ Abriendo…" : loading ? "Enviando…" : "OK — Abrir en VS Code Chat" })] })] }) }));
}

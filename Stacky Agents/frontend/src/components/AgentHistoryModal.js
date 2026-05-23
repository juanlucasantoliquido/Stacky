import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Agents } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentHistoryModal.module.css";
const STATUS_LABEL = {
    queued: "en cola",
    running: "ejecutando",
    completed: "completada",
    error: "con error",
    cancelled: "cancelada",
    discarded: "descartada",
};
const VERDICT_LABEL = {
    approved: "aprobado",
    discarded: "descartado",
};
export default function AgentHistoryModal({ filename, displayName, avatarValue, onClose, }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        Agents.history(filename, 50)
            .then((d) => {
            if (!cancelled)
                setData(d);
        })
            .catch((e) => {
            if (!cancelled)
                setError(String(e?.message ?? e));
        })
            .finally(() => {
            if (!cancelled)
                setLoading(false);
        });
        return () => {
            cancelled = true;
        };
    }, [filename]);
    function handleBackdrop(e) {
        if (e.target === e.currentTarget)
            onClose();
    }
    return (_jsx("div", { className: styles.backdrop, onClick: handleBackdrop, children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "Historial del agente", children: [_jsxs("div", { className: styles.header, children: [_jsx(PixelAvatar, { value: avatarValue, size: "sm", name: displayName }), _jsxs("div", { className: styles.headerText, children: [_jsx("span", { className: styles.agentName, children: displayName }), _jsx("span", { className: styles.subtitle, children: "Historial de tickets" })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), loading && _jsx("div", { className: styles.loading, children: "Cargando historial\u2026" }), !loading && error && (_jsxs("div", { className: styles.error, children: ["\u26A0\uFE0F No se pudo cargar el historial: ", error] })), !loading && !error && data && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.metaBar, children: [_jsxs("span", { className: styles.metaItem, children: ["Tipo inferido: ", _jsx("strong", { children: data.inferred_agent_type })] }), _jsxs("span", { className: styles.metaItem, children: ["Total ejecuciones: ", _jsx("strong", { children: data.total_executions })] })] }), data.tickets.length === 0 ? (_jsx(EmptyHistory, { note: data.mapping_note })) : (_jsx("div", { className: styles.list, children: data.tickets.map((t) => (_jsx(TicketRow, { entry: t }, t.ticket_id))) })), _jsx("div", { className: styles.footnote, children: data.mapping_note })] }))] }) }));
}
function TicketRow({ entry }) {
    const verdict = entry.last_execution_verdict
        ? VERDICT_LABEL[entry.last_execution_verdict] ?? entry.last_execution_verdict
        : null;
    const statusLabel = STATUS_LABEL[entry.last_execution_status] ?? entry.last_execution_status;
    const verdictClass = entry.last_execution_verdict === "approved"
        ? styles.badgeOk
        : entry.last_execution_verdict === "discarded"
            ? styles.badgeBad
            : styles.badgeNeutral;
    return (_jsxs("div", { className: styles.row, children: [_jsxs("div", { className: styles.rowMain, children: [_jsxs("div", { className: styles.ticketMeta, children: [_jsxs("span", { className: styles.ticketId, children: ["ADO-", entry.ado_id] }), entry.ado_state && _jsx("span", { className: styles.state, children: entry.ado_state })] }), _jsx("div", { className: styles.title, title: entry.title, children: entry.title }), _jsxs("div", { className: styles.execMeta, children: [_jsxs("span", { children: ["\u00DAltima ejecuci\u00F3n #", entry.last_execution_id, " \u00B7 ", statusLabel] }), entry.last_execution_started_at && (_jsxs("span", { children: [" \u00B7 ", new Date(entry.last_execution_started_at).toLocaleString()] })), _jsxs("span", { children: [" \u00B7 ", entry.executions_count, " ejecucione", entry.executions_count === 1 ? "" : "s"] })] })] }), _jsxs("div", { className: styles.rowSide, children: [verdict && _jsx("span", { className: `${styles.badge} ${verdictClass}`, children: verdict }), entry.ado_url && (_jsx("a", { className: styles.adoLink, href: entry.ado_url, target: "_blank", rel: "noreferrer", title: "Abrir en Azure DevOps", children: "ADO \u2197" }))] })] }));
}
function EmptyHistory({ note }) {
    return (_jsxs("div", { className: styles.empty, children: [_jsx("div", { className: styles.emptyIcon, children: "\uD83D\uDCED" }), _jsx("div", { className: styles.emptyTitle, children: "Sin historial todav\u00EDa" }), _jsx("div", { className: styles.emptyText, children: note })] }));
}

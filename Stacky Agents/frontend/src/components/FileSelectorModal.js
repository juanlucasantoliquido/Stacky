import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { Tickets } from "../api/endpoints";
import styles from "./FileSelectorModal.module.css";
export default function FileSelectorModal({ ticket, prefix, agentName, loading = false, onConfirm, onCancel, }) {
    const [attachments, setAttachments] = useState([]);
    const [fetchLoading, setFetchLoading] = useState(true);
    const [fetchError, setFetchError] = useState(null);
    const [selected, setSelected] = useState(new Set());
    useEffect(() => {
        setFetchLoading(true);
        setFetchError(null);
        Tickets.attachments(ticket.id)
            .then((res) => {
            const data = res.data ?? res;
            const all = data.attachments ?? [];
            const pfx = prefix.toLowerCase();
            const filtered = pfx
                ? all.filter((a) => a.name.toLowerCase().startsWith(pfx))
                : all;
            setAttachments(filtered);
            // Todos seleccionados por defecto
            setSelected(new Set(filtered.map((a) => a.name)));
            if (data.error)
                setFetchError(data.error);
        })
            .catch((err) => {
            setFetchError(err instanceof Error ? err.message : String(err));
        })
            .finally(() => setFetchLoading(false));
    }, [ticket.id, prefix]);
    function toggleAll() {
        if (selected.size === attachments.length) {
            setSelected(new Set());
        }
        else {
            setSelected(new Set(attachments.map((a) => a.name)));
        }
    }
    function toggle(name) {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(name)) {
                next.delete(name);
            }
            else {
                next.add(name);
            }
            return next;
        });
    }
    function formatSize(bytes) {
        if (bytes < 1024)
            return `${bytes} B`;
        if (bytes < 1024 * 1024)
            return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
    const allSelected = attachments.length > 0 && selected.size === attachments.length;
    const noneSelected = selected.size === 0;
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => e.target === e.currentTarget && onCancel(), children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", children: [_jsxs("div", { className: styles.header, children: [_jsx("div", { className: styles.headerIcon, children: "\uD83D\uDCC2" }), _jsxs("div", { className: styles.headerText, children: [_jsx("span", { className: styles.title, children: "Seleccionar ficheros de entrada" }), _jsxs("span", { className: styles.subtitle, children: ["Agente: ", _jsx("strong", { children: agentName }), " \u00B7 Ticket: ", _jsxs("strong", { children: ["#", ticket.ado_id] })] })] }), _jsx("button", { className: styles.closeBtn, onClick: onCancel, title: "Cancelar", children: "\u2715" })] }), _jsxs("div", { className: styles.prefixRow, children: [_jsx("span", { className: styles.prefixLabel, children: "Prefijo configurado:" }), _jsx("span", { className: styles.prefixBadge, children: prefix || "(todos)" }), _jsx("span", { className: styles.modeBadge, children: "BATCH" })] }), _jsxs("div", { className: styles.body, children: [fetchLoading && (_jsxs("div", { className: styles.centered, children: [_jsx("span", { className: styles.spinner }), "Cargando adjuntos\u2026"] })), !fetchLoading && fetchError && (_jsxs("div", { className: styles.error, children: ["\u26A0\uFE0F ", fetchError] })), !fetchLoading && !fetchError && attachments.length === 0 && (_jsxs("div", { className: styles.empty, children: ["No hay ficheros adjuntos que empiecen por ", _jsx("strong", { children: prefix || "*" }), " en este ticket."] })), !fetchLoading && !fetchError && attachments.length > 0 && (_jsxs(_Fragment, { children: [_jsx("div", { className: styles.selectAll, children: _jsxs("label", { className: styles.checkRow, children: [_jsx("input", { type: "checkbox", checked: allSelected, onChange: toggleAll, className: styles.checkbox }), _jsxs("span", { className: styles.selectAllLabel, children: ["Seleccionar todos (", attachments.length, ")"] })] }) }), _jsx("div", { className: styles.fileList, children: attachments.map((att) => (_jsxs("label", { className: styles.fileRow, children: [_jsx("input", { type: "checkbox", checked: selected.has(att.name), onChange: () => toggle(att.name), className: styles.checkbox }), _jsx("span", { className: styles.fileName, title: att.name, children: att.name }), _jsx("span", { className: styles.fileSize, children: formatSize(att.size) })] }, att.id))) })] }))] }), _jsxs("div", { className: styles.footer, children: [_jsxs("span", { className: styles.selCount, children: [selected.size, " de ", attachments.length, " seleccionados"] }), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.cancelBtn, onClick: onCancel, disabled: loading, children: "Cancelar" }), _jsx("button", { className: styles.confirmBtn, onClick: () => onConfirm(Array.from(selected)), disabled: loading || fetchLoading || noneSelected, children: loading ? "Enviando…" : `⚡ Ejecutar Batch (${selected.size})` })] })] })] }) }));
}

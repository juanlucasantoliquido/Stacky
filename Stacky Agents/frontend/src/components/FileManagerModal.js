import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React from "react";
import { Tickets } from "../api/endpoints";
import styles from "./FileManagerModal.module.css";
function formatSize(bytes) {
    if (bytes < 1024)
        return `${bytes} B`;
    if (bytes < 1024 * 1024)
        return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
export default function FileManagerModal({ ticketId, ticketLabel, onClose }) {
    const [attachments, setAttachments] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    const [selected, setSelected] = React.useState(new Set());
    const [deleting, setDeleting] = React.useState(false);
    const [resultMsg, setResultMsg] = React.useState(null);
    async function loadAttachments() {
        setLoading(true);
        setError(null);
        try {
            const res = await Tickets.attachments(ticketId);
            const data = res.data ?? res;
            setAttachments(data.attachments ?? []);
            if (data.error)
                setError(data.error);
        }
        catch (e) {
            setError(String(e?.message ?? e));
        }
        finally {
            setLoading(false);
        }
    }
    React.useEffect(() => {
        loadAttachments();
    }, [ticketId]);
    function toggleFile(id) {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id))
                next.delete(id);
            else
                next.add(id);
            return next;
        });
    }
    function toggleAll() {
        if (!attachments)
            return;
        if (selected.size === attachments.length) {
            setSelected(new Set());
        }
        else {
            setSelected(new Set(attachments.map((a) => a.id)));
        }
    }
    async function handleDelete() {
        if (!attachments || selected.size === 0)
            return;
        setDeleting(true);
        setResultMsg(null);
        const toDelete = attachments
            .filter((a) => selected.has(a.id))
            .map((a) => ({ id: a.id, url: a.url, name: a.name }));
        try {
            const res = await Tickets.deleteAttachments(ticketId, toDelete);
            const data = res.data ?? res;
            const deleted = data.deleted ?? [];
            const errs = data.errors ?? [];
            let msg = `${deleted.length} adjunto${deleted.length !== 1 ? "s" : ""} borrado${deleted.length !== 1 ? "s" : ""}`;
            if (errs.length > 0) {
                // Si todos los errores tienen el mismo motivo, mostrarlo una vez
                const uniqueReasons = [...new Set(errs.map((e) => e.error))];
                const reasonText = uniqueReasons.length === 1
                    ? ` — ${uniqueReasons[0]}`
                    : ` — ${errs.map((e) => `${e.name}: ${e.error}`).join("; ")}`;
                msg += ` · ${errs.length} error${errs.length !== 1 ? "es" : ""}${reasonText}`;
            }
            setResultMsg({ text: msg, isError: errs.length > 0 });
            setSelected(new Set());
            await loadAttachments();
        }
        catch (e) {
            setResultMsg({ text: String(e?.message ?? e), isError: true });
        }
        finally {
            setDeleting(false);
        }
    }
    const allSelected = !!attachments && attachments.length > 0 && selected.size === attachments.length;
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.modal, children: [_jsxs("div", { className: styles.header, children: [_jsxs("span", { className: styles.title, children: ["Adjuntos del ticket", " ", _jsx("span", { className: styles.subtitle, children: ticketLabel })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "X" })] }), loading && _jsx("div", { className: styles.loading, children: "Cargando adjuntos..." }), !loading && error && _jsx("div", { className: styles.error, children: error }), !loading && attachments !== null && (_jsxs("div", { className: styles.body, children: [attachments.length > 0 && (_jsxs("div", { className: styles.toolbar, children: [_jsx("button", { className: styles.selectAllBtn, onClick: toggleAll, children: allSelected ? "Deseleccionar todo" : "Seleccionar todo" }), selected.size > 0 && (_jsxs("span", { className: styles.selectedCount, children: [selected.size, " seleccionado", selected.size !== 1 ? "s" : ""] })), _jsx("button", { className: styles.deleteBtn, disabled: selected.size === 0 || deleting, onClick: handleDelete, children: deleting ? "Borrando..." : "Borrar (" + selected.size + ")" })] })), _jsx("div", { className: styles.fileList, children: attachments.length === 0 ? (_jsx("div", { className: styles.empty, children: "No hay adjuntos en este ticket." })) : (attachments.map((a) => {
                                const isSel = selected.has(a.id);
                                return (_jsxs("div", { className: styles.fileRow + (isSel ? " " + styles.fileRowSelected : ""), onClick: () => toggleFile(a.id), children: [_jsx("input", { type: "checkbox", className: styles.fileCheck, checked: isSel, onChange: () => toggleFile(a.id), onClick: (e) => e.stopPropagation() }), _jsx("span", { className: styles.fileName, title: a.name, children: a.name }), _jsxs("span", { className: styles.fileMeta, children: [formatSize(a.size), a.created_at ? " " + new Date(a.created_at).toLocaleString() : ""] })] }, a.id));
                            })) }), resultMsg && (_jsx("div", { className: styles.resultMsg + (resultMsg.isError ? " " + styles.resultMsgError : ""), children: resultMsg.text }))] }))] }) }));
}

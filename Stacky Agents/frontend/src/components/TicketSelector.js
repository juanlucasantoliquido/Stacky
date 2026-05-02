import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./TicketSelector.module.css";
export default function TicketSelector() {
    const [search, setSearch] = useState("");
    const [feedback, setFeedback] = useState(null);
    const { activeTicketId, setActiveTicket } = useWorkbench();
    const queryClient = useQueryClient();
    const { data, isLoading } = useQuery({
        queryKey: ["tickets"],
        queryFn: Tickets.list,
        refetchInterval: 60_000,
    });
    const sync = useMutation({
        mutationFn: Tickets.sync,
        onSuccess: (res) => {
            if (res.ok) {
                setFeedback(`Sincronizado: ${res.fetched ?? 0} traídos · ${res.created ?? 0} nuevos · ${res.updated ?? 0} actualizados`);
            }
            else {
                setFeedback(res.message ?? "Error al sincronizar");
            }
            queryClient.invalidateQueries({ queryKey: ["tickets"] });
        },
        onError: (err) => {
            setFeedback(err.message || "Error al sincronizar");
        },
    });
    const tickets = (data ?? []).filter((t) => {
        if (!search)
            return true;
        const q = search.toLowerCase();
        return t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q);
    });
    return (_jsxs("section", { className: styles.section, children: [_jsxs("div", { className: styles.header, children: [_jsx("h3", { className: styles.title, children: "TICKETS" }), _jsxs("button", { type: "button", className: styles.refresh, onClick: () => {
                            setFeedback(null);
                            sync.mutate();
                        }, disabled: sync.isPending, title: "Actualizar tickets desde Azure DevOps", children: [sync.isPending ? "↻" : "⟳", " ", sync.isPending ? "Actualizando…" : "Actualizar"] })] }), _jsx("input", { className: styles.search, placeholder: "Buscar...", value: search, onChange: (e) => setSearch(e.target.value) }), feedback && _jsx("div", { className: styles.feedback, children: feedback }), _jsxs("div", { className: styles.list, children: [isLoading && _jsx("div", { className: "muted", children: "cargando\u2026" }), !isLoading && tickets.length === 0 && (_jsx("div", { className: "muted", children: "sin tickets" })), tickets.map((t) => (_jsx(Row, { ticket: t, active: t.id === activeTicketId, onSelect: () => setActiveTicket(t.id) }, t.id)))] })] }));
}
function Row({ ticket, active, onSelect, }) {
    return (_jsxs("button", { className: `${styles.row} ${active ? styles.active : ""}`, onClick: onSelect, children: [_jsxs("div", { className: styles.rowHead, children: [_jsxs("span", { className: styles.adoId, children: ["ADO-", ticket.ado_id] }), _jsx("span", { className: styles.state, children: ticket.ado_state ?? "—" })] }), _jsx("div", { className: styles.rowTitle, children: ticket.title }), ticket.last_execution && (_jsxs("div", { className: styles.rowMeta, children: ["\u00FAltima: ", ticket.last_execution.agent_type, " \u2022", " ", ticket.last_execution.status] }))] }));
}

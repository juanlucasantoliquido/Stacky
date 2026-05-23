import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
/*
 * FA-45 + FA-14 — Panel desplegable con ejecuciones similares + graveyard.
 * - "Similares aprobadas" (FA-45): top-K execs aprobadas parecidas al ticket actual.
 * - "Graveyard" (FA-14): execs descartadas / fallidas que matchean el query del operador.
 * Se abre desde el editor con un botón. No bloquea la UI.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Similarity } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./SimilarPanel.module.css";
export default function SimilarPanel() {
    const { activeTicketId, activeAgentType, setActiveExecution } = useWorkbench();
    const [open, setOpen] = useState(false);
    const [tab, setTab] = useState("approved");
    const [graveyardQuery, setGraveyardQuery] = useState("");
    const approvedQ = useQuery({
        queryKey: ["similar-approved", activeTicketId, activeAgentType],
        queryFn: () => Similarity.forTicket(activeTicketId, activeAgentType ?? undefined, 5),
        enabled: open && tab === "approved" && activeTicketId != null,
    });
    const graveyardQ = useQuery({
        queryKey: ["graveyard", graveyardQuery, activeAgentType],
        queryFn: () => Similarity.graveyard(graveyardQuery, activeAgentType ?? undefined, 10),
        enabled: open && tab === "graveyard" && graveyardQuery.length >= 3,
    });
    if (!activeTicketId)
        return null;
    return (_jsxs("div", { className: styles.wrapper, children: [_jsxs("button", { className: styles.toggle, onClick: () => setOpen((v) => !v), title: "Buscar ejecuciones similares aprobadas (FA-45) o descartadas (FA-14)", children: ["\uD83D\uDD0D ", open ? "Ocultar" : "Buscar similares & graveyard"] }), open && (_jsxs("div", { className: styles.panel, children: [_jsxs("div", { className: styles.tabs, children: [_jsx("button", { className: `${styles.tab} ${tab === "approved" ? styles.active : ""}`, onClick: () => setTab("approved"), children: "\u2713 Similares aprobadas" }), _jsx("button", { className: `${styles.tab} ${tab === "graveyard" ? styles.active : ""}`, onClick: () => setTab("graveyard"), children: "\u26B0 Graveyard" })] }), tab === "approved" && (_jsx(ResultList, { loading: approvedQ.isLoading, hits: approvedQ.data ?? [], onClick: setActiveExecution, empty: "No hay ejecuciones similares aprobadas todav\u00EDa." })), tab === "graveyard" && (_jsxs(_Fragment, { children: [_jsx("input", { className: styles.search, placeholder: "Texto a buscar (m\u00EDn. 3 caracteres)...", value: graveyardQuery, onChange: (e) => setGraveyardQuery(e.target.value) }), graveyardQuery.length >= 3 && (_jsx(ResultList, { loading: graveyardQ.isLoading, hits: graveyardQ.data ?? [], onClick: setActiveExecution, empty: "Nada en el graveyard que coincida. Prob\u00E1 otro t\u00E9rmino." }))] }))] }))] }));
}
function ResultList({ loading, hits, onClick, empty, }) {
    if (loading)
        return _jsx("div", { className: "muted", style: { padding: 8 }, children: "buscando\u2026" });
    if (hits.length === 0)
        return _jsx("div", { className: "muted", style: { padding: 8 }, children: empty });
    return (_jsx("ul", { className: styles.list, children: hits.map((h) => (_jsx("li", { children: _jsxs("button", { className: styles.item, onClick: () => onClick(h.execution_id), children: [_jsxs("div", { className: styles.itemHead, children: [_jsxs("span", { className: styles.score, children: [Math.round(h.score * 100), "%"] }), _jsxs("span", { className: styles.execId, children: ["#", h.execution_id] }), _jsx("span", { className: styles.agent, children: h.agent_type }), _jsxs("span", { className: styles.ticket, children: ["ADO-", h.ticket_ado_id] }), _jsx("span", { className: styles.verdict, "data-v": h.verdict ?? "", children: h.verdict ?? "" })] }), _jsx("div", { className: styles.snippet, children: h.snippet || "(sin snippet)" })] }) }, h.execution_id))) }));
}

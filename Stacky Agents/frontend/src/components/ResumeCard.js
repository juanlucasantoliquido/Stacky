import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ResumeCard.module.css";
function relativeMinutes(iso) {
    if (!iso)
        return "";
    const ts = Date.parse(iso);
    if (Number.isNaN(ts))
        return "";
    const mins = Math.max(1, Math.round((Date.now() - ts) / 60000));
    if (mins < 60)
        return `hace ${mins} min`;
    const hours = Math.round(mins / 60);
    return `hace ${hours} h`;
}
const AGENT_LABEL = {
    business: "Business",
    functional: "Functional",
    technical: "Technical",
    developer: "Developer",
    qa: "QA",
};
export default function ResumeCard({ projectName, onResume }) {
    const [data, setData] = useState(null);
    const [dismissed, setDismissed] = useState(false);
    useEffect(() => {
        const url = projectName
            ? `/api/session/resume?project=${encodeURIComponent(projectName)}`
            : "/api/session/resume";
        api
            .get(url)
            .then(setData)
            .catch(() => setData(null));
    }, [projectName]);
    if (!data || !data.has_activity || dismissed || !data.last_execution)
        return null;
    const exec = data.last_execution;
    const ticket = data.ticket;
    const next = data.next_agent_suggested;
    return (_jsxs("div", { className: styles.card, role: "region", "aria-label": "Continuar donde lo dejaste", children: [_jsx("div", { className: styles.iconCol, children: _jsx("span", { className: styles.icon, "aria-hidden": "true", children: "\uD83D\uDCCC" }) }), _jsxs("div", { className: styles.body, children: [_jsxs("div", { className: styles.header, children: [_jsx("strong", { children: "Continuar donde lo dejaste" }), _jsx("span", { className: styles.muted, children: relativeMinutes(exec.started_at) })] }), _jsx("div", { className: styles.ticketLine, children: ticket ? (_jsxs(_Fragment, { children: [_jsxs("span", { className: styles.ticketId, children: ["T-", ticket.ado_id] }), _jsx("span", { className: styles.ticketTitle, children: ticket.title })] })) : (_jsx("span", { className: styles.muted, children: "(ticket no encontrado)" })) }), _jsxs("div", { className: styles.metaLine, children: ["\u00DAltimo agente: ", _jsx("strong", { children: AGENT_LABEL[exec.agent_type] ?? exec.agent_type }), next ? (_jsxs(_Fragment, { children: [" · ", "Pr\u00F3ximo sugerido: ", _jsx("strong", { children: AGENT_LABEL[next] ?? next })] })) : null] })] }), _jsxs("div", { className: styles.actions, children: [_jsx("button", { className: styles.primaryBtn, onClick: () => {
                            if (ticket && onResume)
                                onResume(ticket.id, next ?? null);
                        }, disabled: !ticket, children: "Continuar" }), _jsx("button", { className: styles.secondaryBtn, onClick: () => setDismissed(true), children: "Empezar fresco" })] })] }));
}

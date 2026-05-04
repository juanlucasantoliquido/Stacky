import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Packs } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./PackList.module.css";
export default function PackList() {
    const { activeTicketId } = useWorkbench();
    const { data } = useQuery({ queryKey: ["packs"], queryFn: Packs.list });
    const start = useMutation({
        mutationFn: (pack_id) => Packs.start({ pack_id, ticket_id: activeTicketId }),
    });
    return (_jsxs("section", { className: styles.section, children: [_jsx("h3", { className: styles.title, children: "PACKS" }), _jsx("div", { className: styles.list, children: (data ?? []).map((p) => (_jsxs("button", { className: styles.row, disabled: !activeTicketId || start.isPending, onClick: () => start.mutate(p.id), title: p.description, children: [_jsx("span", { className: styles.play, children: "\u25B6" }), _jsx("span", { className: styles.name, children: p.name }), _jsxs("span", { className: styles.steps, children: [p.steps.length, " pasos"] })] }, p.id))) }), !activeTicketId && (_jsx("span", { className: "muted", style: { fontSize: 10 }, children: "eleg\u00ED un ticket primero" })), start.isSuccess && (_jsxs("span", { style: { fontSize: 11, color: "var(--success)" }, children: ["pack iniciado: run #", start.data.id] }))] }));
}

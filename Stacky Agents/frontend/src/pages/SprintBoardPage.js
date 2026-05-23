import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * SprintBoardPage — Tablero de Compromiso de Sprint (Feature A).
 *
 * Vista Kanban simplificada (sin drag-and-drop) del sprint activo en ADO.
 * Solo lectura — no modifica nada en ADO.
 *
 * Grupos: New, Active, Resolved, Done, Blocked.
 * KPIs: story points comprometidos vs completados, items totales vs done.
 *
 * Requiere que el proyecto activo tenga tracker_type=azure_devops y
 * que haya iteraciones configuradas en ADO.
 */
import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import styles from "./SprintBoardPage.module.css";
const GROUP_ORDER = ["New", "Active", "Resolved", "Done", "Blocked"];
function priorityClass(p) {
    switch (p) {
        case 1: return styles.p1;
        case 2: return styles.p2;
        case 3: return styles.p3;
        default: return styles.p4;
    }
}
function formatDate(iso) {
    if (!iso)
        return "—";
    try {
        return new Date(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
    }
    catch {
        return iso.slice(0, 10);
    }
}
function SprintCard({ item }) {
    const initials = item.assigned_to
        ? item.assigned_to.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()
        : "?";
    return (_jsxs("div", { className: styles.card, children: [_jsxs("div", { className: styles.cardId, children: [item.work_item_type, " \u00B7 ADO-", item.ado_id] }), _jsx("div", { className: styles.cardTitle, children: item.title }), _jsxs("div", { className: styles.cardMeta, children: [item.priority && (_jsxs("span", { className: `${styles.priority} ${priorityClass(item.priority)}`, children: ["P", item.priority] })), item.story_points > 0 && _jsxs("span", { children: [item.story_points, " pts"] }), _jsx("span", { title: item.assigned_to || "Sin asignar", style: { fontWeight: 500 }, children: initials }), item.days_in_state !== null && (_jsxs("span", { className: styles.days, children: [item.days_in_state, "d en estado"] }))] })] }));
}
export function SprintBoardPage() {
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ["sprint-board"],
        queryFn: () => api.get("/api/pm/sprint/board"),
        refetchInterval: 5 * 60_000, // refrescar cada 5 minutos
        staleTime: 2 * 60_000,
    });
    const handleRefresh = useCallback(() => refetch(), [refetch]);
    if (isLoading) {
        return (_jsx("div", { className: styles.root, children: _jsx("div", { className: styles.loading, children: "Cargando sprint activo..." }) }));
    }
    if (error || !data) {
        return (_jsx("div", { className: styles.root, children: _jsxs("div", { className: styles.error, children: ["Error al cargar el Sprint Board. Verificar configuracion de ADO.", error instanceof Error && _jsxs(_Fragment, { children: [" (", error.message, ")"] })] }) }));
    }
    if (!data.ok || !data.sprint) {
        return (_jsxs("div", { className: styles.root, children: [_jsx("div", { className: styles.header, children: _jsx("h2", { className: styles.headerTitle, children: "Sprint Board" }) }), _jsxs("div", { className: styles.noSprint, children: [data.message || "No hay sprint activo configurado en ADO.", _jsx("br", {}), _jsx("small", { children: "Configura iteraciones en el proyecto Azure DevOps para usar esta vista." })] })] }));
    }
    const sprint = data.sprint;
    const totals = data.totals;
    const groups = data.groups || {};
    // Ordenar grupos segun GROUP_ORDER y agregar los que no estan en el orden
    const orderedKeys = [
        ...GROUP_ORDER.filter(g => groups[g] !== undefined),
        ...Object.keys(groups).filter(g => !GROUP_ORDER.includes(g)),
    ];
    const spProgress = totals.story_points_committed > 0
        ? Math.round(totals.story_points_done / totals.story_points_committed * 100)
        : 0;
    return (_jsxs("div", { className: styles.root, children: [_jsxs("div", { className: styles.header, children: [_jsx("h2", { className: styles.headerTitle, children: "Sprint Board" }), _jsxs("div", { className: styles.sprintMeta, children: [_jsx("strong", { children: sprint.name }), sprint.start && sprint.end && (_jsxs(_Fragment, { children: [" \u00B7 ", formatDate(sprint.start), " \u2014 ", formatDate(sprint.end)] })), _jsx("button", { style: { marginLeft: 12, fontSize: 11, cursor: "pointer", border: "none", background: "none", color: "#6b7280", textDecoration: "underline" }, onClick: handleRefresh, children: "Actualizar" })] })] }), _jsxs("div", { className: styles.kpiRow, children: [_jsxs("div", { className: styles.kpi, children: [_jsxs("span", { className: styles.kpiValue, children: [totals.items_done, "/", totals.items_total] }), _jsx("span", { className: styles.kpiLabel, children: "Items completados" })] }), _jsxs("div", { className: styles.kpi, children: [_jsx("span", { className: styles.kpiValue, children: totals.story_points_done }), _jsx("span", { className: styles.kpiLabel, children: "SP completados" })] }), _jsxs("div", { className: styles.kpi, children: [_jsx("span", { className: styles.kpiValue, children: totals.story_points_committed }), _jsx("span", { className: styles.kpiLabel, children: "SP comprometidos" })] }), _jsxs("div", { className: styles.kpi, children: [_jsxs("span", { className: styles.kpiValue, children: [spProgress, "%"] }), _jsx("span", { className: styles.kpiLabel, children: "Avance SP" })] }), groups["Blocked"] && groups["Blocked"].length > 0 && (_jsxs("div", { className: styles.kpi, style: { borderColor: "#fca5a5" }, children: [_jsx("span", { className: styles.kpiValue, style: { color: "#b91c1c" }, children: groups["Blocked"].length }), _jsx("span", { className: styles.kpiLabel, children: "Bloqueados" })] }))] }), _jsx("div", { className: styles.board, children: orderedKeys.map((groupName) => {
                    const items = groups[groupName] || [];
                    return (_jsxs("div", { className: styles.column, children: [_jsxs("div", { className: `${styles.columnHeader} ${styles[groupName] || ""}`, children: [_jsx("span", { children: groupName }), _jsx("span", { className: styles.count, children: items.length })] }), _jsx("div", { className: styles.columnBody, children: items.length === 0 ? (_jsx("div", { style: { fontSize: 11, color: "#9ca3af", padding: "8px 4px" }, children: "Sin items" })) : (items.map((item) => (_jsx(SprintCard, { item: item }, item.ado_id)))) })] }, groupName));
                }) })] }));
}
export default SprintBoardPage;

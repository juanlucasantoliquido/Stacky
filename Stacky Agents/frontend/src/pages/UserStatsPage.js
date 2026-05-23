import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * UserStatsPage — Panel de estadisticas de tickets por usuario (P6-Panel).
 *
 * Muestra para cada persona con ado_unique_name configurado:
 * - Tickets actuales por estado (en vivo desde BD local)
 * - Tickets historicos por estado (acumulado desde ticket_state_history)
 *
 * Opcion B implementada (snapshots locales via ticket_state_history).
 * No hace llamadas on-demand a ADO.
 */
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
const STATE_ORDER = ["New", "Active", "In Progress", "Committed", "Resolved", "Done", "Closed", "Blocked", "Removed"];
function StateBar({ byState, total }) {
    if (total === 0)
        return _jsx("span", { style: { fontSize: 11, color: "#9ca3af" }, children: "Sin tickets" });
    const ordered = STATE_ORDER.filter(s => byState[s] > 0)
        .concat(Object.keys(byState).filter(s => !STATE_ORDER.includes(s) && byState[s] > 0));
    return (_jsx("div", { style: { display: "flex", gap: 6, flexWrap: "wrap" }, children: ordered.map(state => (_jsxs("span", { style: {
                fontSize: 11,
                padding: "2px 7px",
                borderRadius: 4,
                background: state === "Done" || state === "Closed" ? "#f0fdf4" : "#f3f4f6",
                color: state === "Done" || state === "Closed" ? "#16a34a" : "#374151",
                border: "1px solid #e5e7eb",
            }, children: [state, ": ", _jsx("strong", { children: byState[state] })] }, state))) }));
}
export function UserStatsPage() {
    const [filter, setFilter] = useState("");
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ["user-stats"],
        queryFn: () => api.get("/api/tickets/user-stats"),
        staleTime: 60_000,
    });
    const syncUsersMutation = useMutation({
        mutationFn: () => api.post("/api/tickets/users/sync-from-ado", {}),
        onSuccess: () => refetch(),
    });
    const users = data?.users ?? [];
    const filtered = filter
        ? users.filter(u => u.ado_unique_name.toLowerCase().includes(filter.toLowerCase()) ||
            u.display_name.toLowerCase().includes(filter.toLowerCase()))
        : users;
    return (_jsxs("div", { style: { padding: "20px 24px", maxWidth: 900 }, children: [_jsxs("div", { style: { display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }, children: [_jsx("h2", { style: { fontSize: 18, fontWeight: 600, margin: 0 }, children: "Estadisticas por Usuario" }), _jsx("button", { style: {
                            padding: "5px 12px", fontSize: 12, border: "1px solid #d1d5db",
                            borderRadius: 5, cursor: "pointer", background: "transparent",
                        }, onClick: () => syncUsersMutation.mutate(), disabled: syncUsersMutation.isPending, children: syncUsersMutation.isPending ? "Sincronizando..." : "Sincronizar usuarios desde ADO" }), syncUsersMutation.data && (_jsxs("span", { style: { fontSize: 11, color: "#16a34a" }, children: [syncUsersMutation.data.created, " creados, ", syncUsersMutation.data.updated, " actualizados"] }))] }), _jsx("div", { style: { marginBottom: 12 }, children: _jsx("input", { type: "text", placeholder: "Filtrar por nombre o email...", value: filter, onChange: e => setFilter(e.target.value), style: {
                        padding: "6px 12px", fontSize: 13, border: "1px solid #d1d5db",
                        borderRadius: 6, width: 280,
                    } }) }), isLoading && (_jsx("div", { style: { color: "#6b7280", padding: "20px 0" }, children: "Cargando estadisticas..." })), error && (_jsx("div", { style: { color: "#b91c1c", padding: "12px 16px", background: "#fef2f2", borderRadius: 6 }, children: "Error al cargar estadisticas." })), !isLoading && !error && filtered.length === 0 && (_jsx("div", { style: { color: "#6b7280", padding: "20px 0" }, children: users.length === 0
                    ? "No hay usuarios configurados. Usa 'Sincronizar usuarios desde ADO' para poblar la lista."
                    : "Sin resultados para el filtro actual." })), filtered.map(user => (_jsxs("div", { style: {
                    border: "1px solid #e5e7eb",
                    borderRadius: 8,
                    padding: "14px 16px",
                    marginBottom: 12,
                    background: "white",
                }, children: [_jsxs("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }, children: [_jsxs("div", { children: [_jsx("div", { style: { fontWeight: 600, fontSize: 14 }, children: user.display_name }), _jsx("div", { style: { fontSize: 11, color: "#6b7280" }, children: user.ado_unique_name }), user.skills.length > 0 && (_jsxs("div", { style: { fontSize: 11, color: "#6b7280", marginTop: 2 }, children: ["Skills: ", user.skills.join(", ")] }))] }), _jsxs("div", { style: { textAlign: "right", fontSize: 12 }, children: [_jsxs("div", { style: { fontWeight: 600, color: "#1d4ed8" }, children: [user.current_tickets.total, " / ", user.max_active_tickets] }), _jsx("div", { style: { fontSize: 10, color: "#9ca3af" }, children: "tickets activos / max" })] })] }), _jsxs("div", { style: { marginBottom: 8 }, children: [_jsxs("div", { style: { fontSize: 11, fontWeight: 500, color: "#374151", marginBottom: 4 }, children: ["Actuales (", user.current_tickets.total, " total)"] }), _jsx(StateBar, { byState: user.current_tickets.by_state, total: user.current_tickets.total })] }), _jsxs("div", { children: [_jsxs("div", { style: { fontSize: 11, fontWeight: 500, color: "#374151", marginBottom: 4 }, children: ["Historico acumulado (", user.historical_tickets.total, " transiciones)"] }), _jsx(StateBar, { byState: user.historical_tickets.by_state, total: user.historical_tickets.total })] })] }, user.ado_unique_name)))] }));
}
export default UserStatsPage;

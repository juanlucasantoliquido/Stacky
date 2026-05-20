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

import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import styles from "./UserStatsPage.module.css";

interface UserStatEntry {
  ado_unique_name: string;
  display_name: string;
  current_tickets: {
    total: number;
    by_state: Record<string, number>;
  };
  historical_tickets: {
    total: number;
    by_state: Record<string, number>;
  };
  max_active_tickets: number;
  skills: string[];
  area_paths: string[];
}

interface UserStatsResponse {
  ok: boolean;
  users: UserStatEntry[];
  total: number;
}

const STATE_ORDER = ["New", "Active", "In Progress", "Committed", "Resolved", "Done", "Closed", "Blocked", "Removed"];

function StateBar({ byState, total }: { byState: Record<string, number>; total: number }) {
  if (total === 0) return <span style={{ fontSize: 11, color: "#9ca3af" }}>Sin tickets</span>;

  const ordered = STATE_ORDER.filter(s => byState[s] > 0)
    .concat(Object.keys(byState).filter(s => !STATE_ORDER.includes(s) && byState[s] > 0));

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {ordered.map(state => (
        <span key={state} style={{
          fontSize: 11,
          padding: "2px 7px",
          borderRadius: 4,
          background: state === "Done" || state === "Closed" ? "#f0fdf4" : "#f3f4f6",
          color: state === "Done" || state === "Closed" ? "#16a34a" : "#374151",
          border: "1px solid #e5e7eb",
        }}>
          {state}: <strong>{byState[state]}</strong>
        </span>
      ))}
    </div>
  );
}

export function UserStatsPage(): React.ReactElement {
  const [filter, setFilter] = useState("");

  const { data, isLoading, error, refetch } = useQuery<UserStatsResponse>({
    queryKey: ["user-stats"],
    queryFn: () => api.get<UserStatsResponse>("/api/tickets/user-stats"),
    staleTime: 60_000,
  });

  const syncUsersMutation = useMutation({
    mutationFn: () => api.post<{ ok: boolean; created: number; updated: number; total: number }>(
      "/api/tickets/users/sync-from-ado",
      {}
    ),
    onSuccess: () => refetch(),
  });

  const users = data?.users ?? [];
  const filtered = filter
    ? users.filter(u =>
        u.ado_unique_name.toLowerCase().includes(filter.toLowerCase()) ||
        u.display_name.toLowerCase().includes(filter.toLowerCase())
      )
    : users;

  return (
    <div style={{ padding: "20px 24px", maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>
          Estadisticas por Usuario
        </h2>
        <button
          style={{
            padding: "5px 12px", fontSize: 12, border: "1px solid #d1d5db",
            borderRadius: 5, cursor: "pointer", background: "transparent",
          }}
          onClick={() => syncUsersMutation.mutate()}
          disabled={syncUsersMutation.isPending}
        >
          {syncUsersMutation.isPending ? "Sincronizando..." : "Sincronizar usuarios desde ADO"}
        </button>
        {syncUsersMutation.data && (
          <span style={{ fontSize: 11, color: "#16a34a" }}>
            {syncUsersMutation.data.created} creados, {syncUsersMutation.data.updated} actualizados
          </span>
        )}
      </div>

      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="Filtrar por nombre o email..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            padding: "6px 12px", fontSize: 13, border: "1px solid #d1d5db",
            borderRadius: 6, width: 280,
          }}
        />
      </div>

      {isLoading && (
        <div style={{ color: "#6b7280", padding: "20px 0" }}>Cargando estadisticas...</div>
      )}

      {error && (
        <div style={{ color: "#b91c1c", padding: "12px 16px", background: "#fef2f2", borderRadius: 6 }}>
          Error al cargar estadisticas.
        </div>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <div style={{ color: "#6b7280", padding: "20px 0" }}>
          {users.length === 0
            ? "No hay usuarios configurados. Usa 'Sincronizar usuarios desde ADO' para poblar la lista."
            : "Sin resultados para el filtro actual."}
        </div>
      )}

      {filtered.map(user => (
        <div key={user.ado_unique_name} style={{
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: "14px 16px",
          marginBottom: 12,
          background: "white",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{user.display_name}</div>
              <div style={{ fontSize: 11, color: "#6b7280" }}>{user.ado_unique_name}</div>
              {user.skills.length > 0 && (
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                  Skills: {user.skills.join(", ")}
                </div>
              )}
            </div>
            <div style={{ textAlign: "right", fontSize: 12 }}>
              <div style={{ fontWeight: 600, color: "#1d4ed8" }}>
                {user.current_tickets.total} / {user.max_active_tickets}
              </div>
              <div style={{ fontSize: 10, color: "#9ca3af" }}>tickets activos / max</div>
            </div>
          </div>

          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 500, color: "#374151", marginBottom: 4 }}>
              Actuales ({user.current_tickets.total} total)
            </div>
            <StateBar byState={user.current_tickets.by_state} total={user.current_tickets.total} />
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 500, color: "#374151", marginBottom: 4 }}>
              Historico acumulado ({user.historical_tickets.total} transiciones)
            </div>
            <StateBar byState={user.historical_tickets.by_state} total={user.historical_tickets.total} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default UserStatsPage;

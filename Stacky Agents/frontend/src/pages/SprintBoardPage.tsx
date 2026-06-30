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

import React, { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import styles from "./SprintBoardPage.module.css";
import { getWorkItemTypeColor } from "../utils/workItemTypeColor";

interface SprintInfo {
  id: string;
  name: string;
  path: string;
  start: string | null;
  end: string | null;
  time_frame: string | null;
}

interface SprintItem {
  ado_id: number;
  title: string;
  state: string;
  work_item_type: string;
  priority: number | null;
  story_points: number;
  assigned_to: string | null;
  assigned_unique_name: string | null;
  tags: string[];
  days_in_state: number | null;
}

interface SprintBoardData {
  ok: boolean;
  sprint: SprintInfo | null;
  groups: Record<string, SprintItem[]>;
  totals: {
    story_points_committed: number;
    story_points_done: number;
    items_total: number;
    items_done: number;
  };
  stale_warning: boolean;
  message?: string;
  error?: string;
}

const GROUP_ORDER = ["New", "Active", "Resolved", "Done", "Blocked"];

function priorityClass(p: number | null): string {
  switch (p) {
    case 1: return styles.p1;
    case 2: return styles.p2;
    case 3: return styles.p3;
    default: return styles.p4;
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
  } catch {
    return iso.slice(0, 10);
  }
}

function SprintCard({ item }: { item: SprintItem }) {
  const initials = item.assigned_to
    ? item.assigned_to.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()
    : "?";

  return (
    <div className={styles.card}>
      <div className={styles.cardId}>
        <span style={{ color: getWorkItemTypeColor(item.work_item_type) }}>
          {item.work_item_type}
        </span> &middot; ADO-{item.ado_id}
      </div>
      <div className={styles.cardTitle}>{item.title}</div>
      <div className={styles.cardMeta}>
        {item.priority && (
          <span className={`${styles.priority} ${priorityClass(item.priority)}`}>
            P{item.priority}
          </span>
        )}
        {item.story_points > 0 && <span>{item.story_points} pts</span>}
        <span title={item.assigned_to || "Sin asignar"} style={{ fontWeight: 500 }}>
          {initials}
        </span>
        {item.days_in_state !== null && (
          <span className={styles.days}>{item.days_in_state}d en estado</span>
        )}
      </div>
    </div>
  );
}

export function SprintBoardPage(): React.ReactElement {
  const { data, isLoading, error, refetch } = useQuery<SprintBoardData>({
    queryKey: ["sprint-board"],
    queryFn: () => api.get<SprintBoardData>("/api/pm/sprint/board"),
    refetchInterval: 5 * 60_000, // refrescar cada 5 minutos
    staleTime: 2 * 60_000,
  });

  const handleRefresh = useCallback(() => refetch(), [refetch]);

  if (isLoading) {
    return (
      <div className={styles.root}>
        <div className={styles.loading}>Cargando sprint activo...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={styles.root}>
        <div className={styles.error}>
          Error al cargar el Sprint Board. Verificar configuracion de ADO.
          {error instanceof Error && <> ({error.message})</>}
        </div>
      </div>
    );
  }

  if (!data.ok || !data.sprint) {
    return (
      <div className={styles.root}>
        <div className={styles.header}>
          <h2 className={styles.headerTitle}>Sprint Board</h2>
        </div>
        <div className={styles.noSprint}>
          {data.message || "No hay sprint activo configurado en ADO."}
          <br />
          <small>Configura iteraciones en el proyecto Azure DevOps para usar esta vista.</small>
        </div>
      </div>
    );
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

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.headerTitle}>Sprint Board</h2>
        <div className={styles.sprintMeta}>
          <strong>{sprint.name}</strong>
          {sprint.start && sprint.end && (
            <> &middot; {formatDate(sprint.start)} — {formatDate(sprint.end)}</>
          )}
          <button
            style={{ marginLeft: 12, fontSize: 11, cursor: "pointer", border: "none", background: "none", color: "#6b7280", textDecoration: "underline" }}
            onClick={handleRefresh}
          >
            Actualizar
          </button>
        </div>
      </div>

      <div className={styles.kpiRow}>
        <div className={styles.kpi}>
          <span className={styles.kpiValue}>{totals.items_done}/{totals.items_total}</span>
          <span className={styles.kpiLabel}>Items completados</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiValue}>{totals.story_points_done}</span>
          <span className={styles.kpiLabel}>SP completados</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiValue}>{totals.story_points_committed}</span>
          <span className={styles.kpiLabel}>SP comprometidos</span>
        </div>
        <div className={styles.kpi}>
          <span className={styles.kpiValue}>{spProgress}%</span>
          <span className={styles.kpiLabel}>Avance SP</span>
        </div>
        {groups["Blocked"] && groups["Blocked"].length > 0 && (
          <div className={styles.kpi} style={{ borderColor: "#fca5a5" }}>
            <span className={styles.kpiValue} style={{ color: "#b91c1c" }}>
              {groups["Blocked"].length}
            </span>
            <span className={styles.kpiLabel}>Bloqueados</span>
          </div>
        )}
      </div>

      <div className={styles.board}>
        {orderedKeys.map((groupName) => {
          const items = groups[groupName] || [];
          return (
            <div key={groupName} className={styles.column}>
              <div className={`${styles.columnHeader} ${styles[groupName] || ""}`}>
                <span>{groupName}</span>
                <span className={styles.count}>{items.length}</span>
              </div>
              <div className={styles.columnBody}>
                {items.length === 0 ? (
                  <div style={{ fontSize: 11, color: "#9ca3af", padding: "8px 4px" }}>Sin items</div>
                ) : (
                  items.map((item) => (
                    <SprintCard key={item.ado_id} item={item} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SprintBoardPage;

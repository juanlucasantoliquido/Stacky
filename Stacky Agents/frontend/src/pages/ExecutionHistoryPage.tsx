/**
 * Plan 39 A2 — Página de historial de ejecuciones.
 *
 * Muestra el endpoint GET /api/executions/history con filtros,
 * paginación y acceso al drawer de detalle (Plan 38 C2).
 */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Executions, type ExecutionHistoryItem } from "../api/endpoints";
import ExecutionDetailDrawer from "../components/ExecutionDetailDrawer";
import GroundingObservatoryCard from "../components/GroundingObservatoryCard";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import { StatusChip } from "../components/ui";
import { runStatusTone, runStatusLabel } from "../utils/runStatus";
import { formatRelativeTime } from "../utils/formatRelativeTime";
import { formatDuration, formatCostUsd } from "../services/format";
import { useWorkbench } from "../store/workbench";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { parseRoute, serializeRoute } from "../services/routes";
import {
  historyFiltersFromQuery, historyFiltersToQuery,
  omitKeys, HISTORY_FILTER_QUERY_KEYS, resolveMountFilters,
} from "../services/routeFilters";
import styles from "./ExecutionHistoryPage.module.css";

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

interface Filters {
  agent_type: string;
  runtime: string;
  status: string;
  days: string;
  limit: number;
  offset: number;
}

const DEFAULT_FILTERS: Filters = {
  agent_type: "",
  runtime: "",
  status: "",
  days: "",
  limit: 50,
  offset: 0,
};

const AGENT_TYPES = ["", "developer", "business", "qa", "critic", "debug", "custom"];
const RUNTIMES = ["", "claude_code_cli", "codex_cli", "github_copilot"];
const STATUSES = ["", "completed", "error", "needs_review", "running", "cancelled"];

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function ExecutionHistoryPage({ exec }: { exec?: number | null }) {
  // Plan 165 F2 — los filtros sobreviven F5 y el cambio de tab vía localStorage.
  const [filters, setFilters] = useLocalStorageState<Filters>("stacky.ui.history.filters", DEFAULT_FILTERS);
  // Plan 165 F3 — el drawer arranca abierto si la ruta trae exec (deep-link / Slack).
  const [detailId, setDetailId] = useState<number | null>(exec ?? null);
  const activeProject = useWorkbench((s) => s.activeProject);

  // Plan 165 F3 (C1) — sincronización con la prop VIVA exec (patrón lastApplied):
  // reacciona SOLO a cambios de exec (popstate / nav in-app / link de Slack).
  // Reemplaza al receptor ?execution= roto: routes.ts (vía App) ya parseó
  // exec/execution y lo pasa como prop. Sin el patrón lastApplied, cerrar el
  // drawer con route.exec aún seteado lo re-abriría (loop prop->estado).
  const lastAppliedExec = useRef(exec);
  useEffect(() => {
    if (exec !== lastAppliedExec.current) {
      lastAppliedExec.current = exec;
      setDetailId(exec ?? null);
    }
  }, [exec]);

  // Plan 165 F3 [A2] — write-back: abrir el drawer por CLICK escribe ?exec=<id>;
  // cerrarlo lo quita. replaceState con guard (sin entradas de historial).
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    if (current.tab !== "history") return;           // guard: solo montada en /history
    const next = serializeRoute({ ...current, exec: detailId ?? undefined });
    const target = window.location.pathname + window.location.search;
    if (next !== target) window.history.replaceState({}, "", next);
  }, [detailId]);

  // Plan 165 F2 — montaje: precedencia URL > persistido > defaults, merge
  // anti-drift (C5) y offset 0 (§3.7). Si la URL trae >=1 filtro, esa vista se
  // reproduce EXACTA (lo persistido se ignora entero — C2).
  useEffect(() => {
    const { query } = parseRoute(window.location.pathname, window.location.search);
    const fromUrl = historyFiltersFromQuery(query);
    setFilters((persisted) => ({
      ...resolveMountFilters(DEFAULT_FILTERS, persisted, fromUrl),
      offset: 0,
    }));
  }, []);  // SOLO al montar

  // Plan 165 F2 — reflejo de filtros en el querystring (replaceState: no ensucia
  // el historial ni serializa offset). parseRoute/serializeRoute preservan exec
  // y toda query ajena vía ...current.
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    const next = serializeRoute({
      ...current,
      query: { ...omitKeys(current.query, HISTORY_FILTER_QUERY_KEYS), ...historyFiltersToQuery(filters) },
    });
    const target = window.location.pathname + window.location.search;
    if (next !== target) {
      window.history.replaceState({}, "", next);
    }
  }, [filters]);

  const historyQ = useQuery({
    queryKey: ["execution-history", filters, activeProject?.name],
    queryFn: () =>
      Executions.history({
        project: activeProject?.name,
        agent_type: filters.agent_type || undefined,
        runtime: filters.runtime || undefined,
        status: filters.status || undefined,
        days: filters.days ? Number(filters.days) : undefined,
        limit: filters.limit,
        offset: filters.offset,
      }),
    staleTime: 30_000,
  });

  const items: ExecutionHistoryItem[] = historyQ.data ?? [];
  const isLoading = historyQ.isLoading;

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((f) => ({ ...f, [key]: value, offset: key !== "offset" ? 0 : (value as number) }));
  }

  function prevPage() {
    setFilter("offset", Math.max(0, filters.offset - filters.limit));
  }

  function nextPage() {
    if (items.length >= filters.limit) {
      setFilter("offset", filters.offset + filters.limit);
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>Historial de ejecuciones</h2>
        <span className={styles.subtitle}>
          {activeProject?.name ?? "Todos los proyectos"} · {isLoading ? "cargando…" : `${items.length} resultado${items.length !== 1 ? "s" : ""}`}
        </span>
      </div>

      {/* Plan 44 F4 — Observatorio de grounding (solo-lectura) */}
      <GroundingObservatoryCard />

      {/* Filtros */}
      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={filters.agent_type}
          onChange={(e) => setFilter("agent_type", e.target.value)}
          aria-label="Filtrar por tipo de agente"
        >
          {AGENT_TYPES.map((a) => (
            <option key={a} value={a}>{a || "Todos los agentes"}</option>
          ))}
        </select>

        <select
          className={styles.filterSelect}
          value={filters.runtime}
          onChange={(e) => setFilter("runtime", e.target.value)}
          aria-label="Filtrar por runtime"
        >
          {RUNTIMES.map((r) => (
            <option key={r} value={r}>{r || "Todos los runtimes"}</option>
          ))}
        </select>

        <select
          className={styles.filterSelect}
          value={filters.status}
          onChange={(e) => setFilter("status", e.target.value)}
          aria-label="Filtrar por estado"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s || "Todos los estados"}</option>
          ))}
        </select>

        <select
          className={styles.filterSelect}
          value={filters.days}
          onChange={(e) => setFilter("days", e.target.value)}
          aria-label="Filtrar por días"
        >
          <option value="">Todos los días</option>
          <option value="1">Últimas 24h</option>
          <option value="7">Últimos 7 días</option>
          <option value="30">Últimos 30 días</option>
          <option value="90">Últimos 90 días</option>
        </select>
      </div>

      {/* Tabla */}
      {isLoading ? (
        <div className={styles.tableWrapper}><SkeletonList rows={8} rowHeight={28} ariaLabel="Cargando historial" /></div>
      ) : (!historyQ.isError && items.length === 0) ? (   // C1: guard vacío-vs-error (§10.7)
        <EmptyState variant="history" />
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Inicio</th>
                <th>Agente</th>
                <th>Runtime</th>
                <th>Modelo</th>
                <th>Estado</th>
                <th>Duración</th>
                <th>Costo</th>
                <th>Prompt</th>
                <th>Archivos</th>
                <th>Ticket</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className={styles.row}
                  onClick={() => setDetailId(item.id)}
                  title="Click para ver detalle"
                >
                  <td className={styles.dateCell}>{formatRelativeTime(item.started_at)}</td>
                  <td>{item.agent_type}</td>
                  <td className={styles.mono}>{item.runtime ?? "—"}</td>
                  <td className={styles.mono}>{item.model ?? "—"}</td>
                  <td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>
                  <td className={styles.numCell}>{formatDuration(item.duration_ms)}</td>
                  <td className={styles.numCell}>{formatCostUsd(item.cost_usd)}</td>
                  <td className={styles.mono}>
                    {item.prompt_sha
                      ? <span title={item.prompt_sha}>{item.prompt_sha.slice(0, 7)}</span>
                      : "—"}
                  </td>
                  <td className={styles.numCell}>{item.produced_files_count}</td>
                  <td className={styles.ticketCell}>
                    {item.ticket_title
                      ? <span title={item.ticket_title}>{item.ticket_title.slice(0, 40)}{item.ticket_title.length > 40 ? "…" : ""}</span>
                      : `#${item.ticket_id}`}
                    {/* Plan 117 — TL;DR + chip de riesgo (A2) */}
                    {item.local_insight?.tldr ? (
                      <div className={styles.insightTldr} title={item.local_insight.tldr}>
                        {item.local_insight.state === "done" && item.local_insight.risk ? (
                          <span
                            className={
                              item.local_insight.risk === "high"
                                ? styles.riskHigh
                                : item.local_insight.risk === "medium"
                                  ? styles.riskMedium
                                  : styles.riskLow
                            }
                          >
                            {item.local_insight.risk}
                          </span>
                        ) : null}
                        {item.local_insight.tldr}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      {!isLoading && (
        <div className={styles.pagination}>
          <button
            className={styles.pageBtn}
            disabled={filters.offset === 0}
            onClick={prevPage}
          >
            Anterior
          </button>
          <span className={styles.pageInfo}>
            {filters.offset + 1}–{filters.offset + items.length}
          </span>
          <button
            className={styles.pageBtn}
            disabled={items.length < filters.limit}
            onClick={nextPage}
          >
            Siguiente
          </button>
        </div>
      )}

      {/* Drawer de detalle (Plan 38 C2) */}
      <ExecutionDetailDrawer
        executionId={detailId}
        onClose={() => setDetailId(null)}
      />
    </div>
  );
}

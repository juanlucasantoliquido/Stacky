import React, { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { SystemLogs, type SystemLogEntry } from "../api/endpoints";
import { formatDate, formatTime, formatDuration, formatInt } from "../services/format";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { parseRoute, serializeRoute } from "../services/routes";
import {
  sysLogFiltersFromQuery, sysLogFiltersToQuery,
  omitKeys, SYSLOG_FILTER_QUERY_KEYS, resolveMountFilters,
} from "../services/routeFilters";
import styles from "./SystemLogsPage.module.css";

const PAGE_SIZE = 100;

// Plan 165 F2 — defaults de los 8 filtros extraídos a una const (usados por el
// hook, el efecto de montaje anti-drift y clearFilters, sin duplicar el literal).
const SYSLOG_DEFAULTS = {
  level: "", source: "", action: "", q: "",
  execution_id: "", ticket_id: "", from: "", to: "",
};

const LEVEL_OPTIONS = ["", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;

function levelClass(level: string): string {
  const map: Record<string, string> = {
    DEBUG: styles.lvlDEBUG,
    INFO: styles.lvlINFO,
    WARNING: styles.lvlWARNING,
    ERROR: styles.lvlERROR,
    CRITICAL: styles.lvlCRITICAL,
  };
  return map[level] ?? styles.lvlINFO;
}

function fmtTs(ts: string): string {
  const d = formatDate(ts);
  return d === "—" ? "—" : `${d} ${formatTime(ts)}`;
}

// ── Detail Modal ────────────────────────────────────────────────────────────

interface DetailModalProps {
  log: SystemLogEntry;
  onClose: () => void;
}

function DetailModal({ log, onClose }: DetailModalProps) {
  const metaFields: [string, unknown][] = [
    ["ID", log.id],
    ["Timestamp", fmtTs(log.timestamp)],
    ["Level", log.level],
    ["Source", log.source],
    ["Action", log.action],
    ["Execution ID", log.execution_id ?? "—"],
    ["Ticket ID", log.ticket_id ?? "—"],
    ["User", log.user ?? "—"],
    ["Request ID", log.request_id ?? "—"],
    ["Method", log.method ?? "—"],
    ["Endpoint", log.endpoint ?? "—"],
    ["Status Code", log.status_code ?? "—"],
    ["Duration", formatDuration(log.duration_ms)],
    ["Tags", log.tags?.join(", ") || "—"],
  ];

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <span className={`${styles.lvl} ${levelClass(log.level)}`}>{log.level}</span>
          <span className={styles.modalTitle}>
            {log.source} › {log.action}
          </span>
          <button className={styles.modalClose} onClick={onClose}>×</button>
        </div>

        <div className={styles.modalBody}>
          {/* Meta grid */}
          <div className={styles.metaGrid}>
            {metaFields.map(([label, value]) => (
              <div key={label} className={styles.metaItem}>
                <div className={styles.metaLabel}>{label}</div>
                <div className={styles.metaValue}>{String(value)}</div>
              </div>
            ))}
          </div>

          {/* Error */}
          {log.error && (
            <div>
              <p className={styles.sectionTitle}>Error</p>
              <div className={styles.errorBlock}>
                <strong>{log.error.type}: {log.error.message}</strong>
                {"\n\n"}
                {log.error.traceback}
              </div>
            </div>
          )}

          {/* Input */}
          {log.input != null && (
            <div>
              <p className={styles.sectionTitle}>Input</p>
              <pre className={styles.codeBlock}>
                {JSON.stringify(log.input, null, 2)}
              </pre>
            </div>
          )}

          {/* Output */}
          {log.output != null && (
            <div>
              <p className={styles.sectionTitle}>Output</p>
              <pre className={styles.codeBlock}>
                {JSON.stringify(log.output, null, 2)}
              </pre>
            </div>
          )}

          {/* Context */}
          {log.context && Object.keys(log.context).length > 0 && (
            <div>
              <p className={styles.sectionTitle}>Context</p>
              <pre className={styles.codeBlock}>
                {JSON.stringify(log.context, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function SystemLogsPage() {
  // Plan 165 F2 — los 8 filtros sobreviven F5 y el cambio de tab vía localStorage.
  const [filters, setFilters] = useLocalStorageState("stacky.ui.syslogs.filters", SYSLOG_DEFAULTS);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SystemLogEntry | null>(null);

  // Plan 165 F2 — montaje: precedencia URL > persistido > defaults, merge
  // anti-drift (C5) y offset 0 (§3.7). offset ya vive aparte (no se persiste).
  useEffect(() => {
    const { query } = parseRoute(window.location.pathname, window.location.search);
    const fromUrl = sysLogFiltersFromQuery(query);
    setFilters((persisted) => resolveMountFilters(SYSLOG_DEFAULTS, persisted, fromUrl));
    setOffset(0);
  }, []);  // SOLO al montar

  // Plan 165 F2 — reflejo de los 8 filtros en el querystring (replaceState: no
  // ensucia el historial). parseRoute/serializeRoute preservan la query ajena.
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    const next = serializeRoute({
      ...current,
      query: { ...omitKeys(current.query, SYSLOG_FILTER_QUERY_KEYS), ...sysLogFiltersToQuery(filters) },
    });
    const target = window.location.pathname + window.location.search;
    if (next !== target) {
      window.history.replaceState({}, "", next);
    }
  }, [filters]);

  const queryParams = {
    level: filters.level || undefined,
    source: filters.source || undefined,
    action: filters.action || undefined,
    q: filters.q || undefined,
    execution_id: filters.execution_id ? parseInt(filters.execution_id) : undefined,
    ticket_id: filters.ticket_id ? parseInt(filters.ticket_id) : undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["system-logs", queryParams],
    queryFn: () => SystemLogs.list(queryParams),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });

  const { data: stats } = useQuery({
    queryKey: ["system-logs-stats"],
    queryFn: () => SystemLogs.stats(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const setFilter = useCallback(<K extends keyof typeof filters>(key: K, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setOffset(0);
  }, []);

  const clearFilters = () => {
    setFilters(SYSLOG_DEFAULTS);
    setOffset(0);
  };

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const exportUrl = SystemLogs.exportUrl({ format: "json", level: filters.level || undefined, source: filters.source || undefined });

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <h2 className={styles.title}>📋 System Logs</h2>

        {stats && (
          <div className={styles.stats}>
            <span className={`${styles.statBadge} ${styles.error}`}>
              ERR {stats.by_level["ERROR"] ?? 0}
            </span>
            <span className={`${styles.statBadge} ${styles.warning}`}>
              WARN {stats.by_level["WARNING"] ?? 0}
            </span>
            <span className={`${styles.statBadge} ${styles.info}`}>
              Total {formatInt(stats.total)}
            </span>
          </div>
        )}

        <span className={styles.spacer} />

        <a
          href={exportUrl}
          download="stacky_logs.json"
          className={styles.exportBtn}
          target="_blank"
          rel="noopener noreferrer"
        >
          ↓ Export JSON
        </a>
        <a
          href={SystemLogs.exportUrl({ format: "csv" })}
          download="stacky_logs.csv"
          className={styles.exportBtn}
          target="_blank"
          rel="noopener noreferrer"
        >
          ↓ Export CSV
        </a>
      </div>

      {/* Filters */}
      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={filters.level}
          onChange={(e) => setFilter("level", e.target.value)}
        >
          {LEVEL_OPTIONS.map((l) => (
            <option key={l} value={l}>{l || "All levels"}</option>
          ))}
        </select>

        <input
          className={`${styles.filterInput} ${styles.wide}`}
          placeholder="Source (e.g. agent_runner)"
          value={filters.source}
          onChange={(e) => setFilter("source", e.target.value)}
        />

        <input
          className={`${styles.filterInput} ${styles.wide}`}
          placeholder="Action (e.g. agent_started)"
          value={filters.action}
          onChange={(e) => setFilter("action", e.target.value)}
        />

        <input
          className={`${styles.filterInput} ${styles.wide}`}
          placeholder="Search text..."
          value={filters.q}
          onChange={(e) => setFilter("q", e.target.value)}
        />

        <input
          className={`${styles.filterInput} ${styles.narrow}`}
          placeholder="Exec ID"
          type="number"
          value={filters.execution_id}
          onChange={(e) => setFilter("execution_id", e.target.value)}
        />

        <input
          className={`${styles.filterInput} ${styles.narrow}`}
          placeholder="Ticket ID"
          type="number"
          value={filters.ticket_id}
          onChange={(e) => setFilter("ticket_id", e.target.value)}
        />

        <input
          className={styles.filterInput}
          type="datetime-local"
          value={filters.from}
          onChange={(e) => setFilter("from", e.target.value)}
          title="From date"
        />

        <input
          className={styles.filterInput}
          type="datetime-local"
          value={filters.to}
          onChange={(e) => setFilter("to", e.target.value)}
          title="To date"
        />

        <button className={styles.clearBtn} onClick={clearFilters}>Clear</button>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        {isLoading ? (
          <div className={styles.empty}>Loading logs…</div>
        ) : items.length === 0 ? (
          <div className={styles.empty}>No logs match the current filters.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Level</th>
                <th>Timestamp</th>
                <th>Source</th>
                <th>Action</th>
                <th>Exec ID</th>
                <th>Ticket</th>
                <th>User</th>
                <th>Method</th>
                <th>Endpoint</th>
                <th>Status</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {items.map((log) => (
                <tr key={log.id} onClick={() => setSelected(log)}>
                  <td>
                    <span className={`${styles.lvl} ${levelClass(log.level)}`}>
                      {log.level}
                    </span>
                  </td>
                  <td title={log.timestamp}>{fmtTs(log.timestamp)}</td>
                  <td title={log.source}>{log.source}</td>
                  <td title={log.action}>{log.action}</td>
                  <td>{log.execution_id ?? "—"}</td>
                  <td>{log.ticket_id ?? "—"}</td>
                  <td>{log.user ?? "—"}</td>
                  <td>{log.method ?? "—"}</td>
                  <td title={log.endpoint ?? ""}>{log.endpoint ?? "—"}</td>
                  <td style={{ color: log.status_code && log.status_code >= 400 ? "#f87171" : undefined }}>
                    {log.status_code ?? "—"}
                  </td>
                  <td>{formatDuration(log.duration_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div className={styles.pagination}>
        <button
          className={styles.pageBtn}
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          ← Prev
        </button>
        <span>
          Page {currentPage} of {totalPages || 1}
        </span>
        <button
          className={styles.pageBtn}
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next →
        </button>
        {isFetching && <span style={{ color: "#a78bfa", fontSize: 11 }}>Refreshing…</span>}
        <span className={styles.total}>{formatInt(total)} total events</span>
      </div>

      {/* Detail Modal */}
      {selected && (
        <DetailModal log={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

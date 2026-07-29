/**
 * Plan 39 A2 — Página de historial de ejecuciones.
 *
 * Muestra el endpoint GET /api/executions/history con filtros,
 * paginación y acceso al drawer de detalle (Plan 38 C2).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Executions, type ExecutionHistoryItem } from "../api/endpoints";
import ExecutionDetailDrawer from "../components/ExecutionDetailDrawer";
import CopyAsButton from "../components/CopyAsButton";
import Toast, { type ToastState } from "../components/Toast";
import BulkActionsBar from "../components/bulk/BulkActionsBar";
import { useRowSelection } from "../components/bulk/useRowSelection";
import { useBulkActionsEnabled } from "../services/bulkFlags";
import { createBulkRunner, summarizeBulk } from "../services/bulkModel";
import { copyText } from "../services/copyService";
import {
  executionHistoryToRows,
  rowsToCsv,
  rowsToMarkdownTable,
  rowsToHtmlTable,
  copiedRowsLabel,
} from "../services/copyFormats";
import GroundingObservatoryCard from "../components/GroundingObservatoryCard";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import { StatusChip, Checkbox, IconButton, Select } from "../components/ui";
import { runStatusTone, runStatusLabel } from "../utils/runStatus";
import { describeVerdict, matchesVerdictLevel, verdictChipTone } from "../utils/runVerdict";
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
import { useRovingFocus } from "../hooks/useRovingFocus";
import { usePrefetchExecutionDetail } from "../hooks/usePrefetchExecutionDetail";
import SavedViewsBar from "../components/SavedViewsBar";
import TableColumnsMenu from "../components/TableColumnsMenu";
import usePeek from "../components/peek/usePeek";
import PeekCard from "../components/peek/PeekCard";
import useEntityContextMenu from "../components/contextmenu/useEntityContextMenu";
import ContextMenu from "../components/contextmenu/ContextMenu";
import { actionsForExecution, quickActions, type EntityActionContext } from "../services/entityActions";
import { copyText as copiarTexto } from "../services/clipboard";
import { buildExecutionPeek } from "../services/peekModel";
import { hydrateUiPref, loadUiPrefLocal, saveUiPref } from "../services/uiPrefs";
import {
  cycleSort,
  EMPTY_TABLE_PREFS,
  HISTORY_COLUMNS,
  isColVisible,
  sanitizeTablePrefs,
  sortToQuery,
  type TablePrefs,
} from "../services/tablePrefs";
import { normalizeFilters } from "../services/savedViews";
import { combinarProps } from "../utils/combinarProps";
import { useUiPerfFlags } from "../hooks/useUiPerfFlags";
import { QUERY_TUNING } from "../services/queryTuning";
import { isUiShortcutsEnabled, withShortcutHint } from "../services/shortcuts";

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

interface Filters {
  agent_type: string;
  runtime: string;
  status: string;
  /** Plan 269 F4 — filtro de PRESENTACION por nivel de veredicto. El backend no
   *  lo conoce: el veredicto se calcula al leer. OPCIONAL a proposito: los
   *  filtros que el operador ya tiene persistidos en localStorage no traen esta
   *  clave, y resolveMountFilters devuelve el objeto sin ella. */
  verdict_level?: string;
  days: string;
  limit: number;
  offset: number;
}

const DEFAULT_FILTERS: Filters = {
  agent_type: "",
  runtime: "",
  status: "",
  verdict_level: "",
  days: "",
  limit: 50,
  offset: 0,
};

const AGENT_TYPES = ["", "developer", "business", "qa", "critic", "debug", "custom"];
const RUNTIMES = ["", "claude_code_cli", "codex_cli", "github_copilot"];
const STATUSES = ["", "completed", "error", "needs_review", "running", "cancelled"];
// Plan 269 F4 — los 3 niveles de VERDICT_LEVELS (services/run_verdict.py) + "sin filtro".
const VERDICT_LEVEL_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Todos los veredictos" },
  { value: "exito", label: "Terminó bien" },
  { value: "advertencia", label: "Con advertencias" },
  { value: "error_real", label: "Error real" },
];

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function ExecutionHistoryPage({ exec }: { exec?: number | null }) {
  const { instantNav } = useUiPerfFlags();
  // Plan 173 F4 — columnas visibles, orden y anchos, por operador.
  const [tablePrefs, setTablePrefs] = useState<TablePrefs>(() =>
    sanitizeTablePrefs(loadUiPrefLocal("table.history", EMPTY_TABLE_PREFS), HISTORY_COLUMNS),
  );
  const tableRef = useRef<HTMLTableElement>(null);
  // Plan 175 — vista previa al hover y menú contextual, cada uno con su flag.
  const [peekEnabled, setPeekEnabled] = useState(false);
  const [ctxMenuEnabled, setCtxMenuEnabled] = useState(false);
  const peek = usePeek(peekEnabled);
  // Feedback de copiado sin toast: un ✓ transitorio en el propio icono.
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const ctxMenu = useEntityContextMenu(ctxMenuEnabled);
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
    // El sort va en la key: sin él, cambiar el orden serviría la página cacheada
    // con el orden viejo y parecería que el click no hizo nada.
    queryKey: ["execution-history", filters, activeProject?.name, tablePrefs.sort],
    queryFn: () =>
      Executions.history({
        project: activeProject?.name,
        agent_type: filters.agent_type || undefined,
        runtime: filters.runtime || undefined,
        status: filters.status || undefined,
        days: filters.days ? Number(filters.days) : undefined,
        limit: filters.limit,
        offset: filters.offset,
        // Plan 173 F4/F5 — el orden elegido se resuelve en el servidor: ordenar
        // solo la página traída daría un orden que cambia al paginar.
        ...sortToQuery(tablePrefs, HISTORY_COLUMNS),
      }),
    ...QUERY_TUNING.history,
    // Plan 174 F4 — mantener la tabla anterior mientras llega la página nueva.
    // Vaciarla en cada filtro/paginado es el flash de vacío más visible del
    // cockpit, y además hace perder la referencia de lo que se estaba leyendo.
    placeholderData: instantNav ? keepPreviousData : undefined,
  });

  const itemsCrudos: ExecutionHistoryItem[] = historyQ.data ?? [];
  // Plan 269 F4 — filtro de PRESENTACION por nivel de veredicto. Se aplica ACA y
  // no dentro del .map para que TODOS los consumidores de `items` (las filas, la
  // seleccion en lote y el copiado) vean exactamente lo mismo: si el filtro
  // viviera solo en el render, "seleccionar todo" marcaria filas ocultas.
  // Interaccion con la paginacion, declarada: la lista viene paginada del
  // servidor, asi que filtrar en cliente puede dejar una pagina con menos filas
  // que `limit`. Es el MISMO comportamiento que ya tiene el filtro `runtime`
  // (que el backend aplica en Python despues de paginar): no se introduce una
  // anomalia nueva, se hereda una conocida.
  const items: ExecutionHistoryItem[] = useMemo(
    () => itemsCrudos.filter((i) => matchesVerdictLevel(i.run_verdict, filters.verdict_level)),
    [itemsCrudos, filters.verdict_level],
  );

  useEffect(() => {
    let vivo = true;
    void fetch("/api/diag/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!vivo || !d) return;
        // Solo un false EXPLÍCITO apaga: las dos son default ON.
        setPeekEnabled(d.ui_peek_enabled !== false);
        setCtxMenuEnabled(d.ui_context_menu_enabled !== false);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  /** Solo se marca el ✓ si el copiado SALIÓ BIEN: decir "copiado" cuando no se
   *  copió hace que el operador pegue lo que tenía antes. */
  function marcarHecho(actionId: string, itemId: number, ok: boolean) {
    if (!ok) return;
    setCopiedId(`${actionId}-${itemId}`);
    setTimeout(() => setCopiedId(null), 1200);
  }

  /** Contexto de ejecución de las acciones. La confirmación es el armado en dos
   *  pasos del propio menú (plan 175 F3), así que acá ya viene resuelta. */
  const accionCtx: EntityActionContext = {
    copyText: copiarTexto,
    openExternal: (url: string) => window.open(url, "_blank", "noopener"),
    openDetail: (id: number) => setDetailId(id),
    navigate: (path: string) => window.history.pushState({}, "", path),
    askConfirm: async () => true,
    api: {
      cancelExecution: (id: number) => Executions.cancel(id),
      deleteExecution: (id: number) => Executions.deleteOne(id),
      publishExecution: (id: number) => Executions.publish(id),
    },
  };

  // Lo local pinta ya; el backend gana cuando llega.
  useEffect(() => {
    let vivo = true;
    void hydrateUiPref("table.history", (raw) =>
      sanitizeTablePrefs(raw, HISTORY_COLUMNS),
    ).then((remoto) => {
      if (vivo && remoto) setTablePrefs(remoto);
    });
    return () => {
      vivo = false;
    };
  }, []);

  // Los anchos se aplican imperativamente: el ratchet del plan 138 no admite
  // estilos inline en el JSX, y acá además cambian al arrastrar.
  useEffect(() => {
    const tabla = tableRef.current;
    if (!tabla) return;
    for (const th of Array.from(tabla.querySelectorAll<HTMLElement>("th[data-col]"))) {
      const ancho = tablePrefs.widths[th.dataset.col ?? ""];
      th.style.width = ancho ? `${ancho}px` : "";
    }
  }, [tablePrefs.widths, items.length]);

  function cambiarPrefs(next: TablePrefs) {
    setTablePrefs(next);
    saveUiPref("table.history", next);
  }

  /** Flecha del encabezado. Solo aparece en la columna que ordena de verdad. */
  function sortMarca(colId: string): string {
    const s = tablePrefs.sort;
    if (!s || s.column !== colId) return "";
    return s.dir === "asc" ? " ▲" : " ▼";
  }
  // Plan 174 F3 — precargar el detalle mientras el operador decide si abrirlo.
  const { getPrefetchProps } = usePrefetchExecutionDetail();
  // Plan 172 F4 — foco roving: j/k o flechas para recorrer, Enter para abrir.
  const roving = useRovingFocus({
    itemCount: items.length,
    onOpen: (i) => items[i] && setDetailId(items[i].id),
    onEscape: () => setDetailId(null),
  });
  const isLoading = historyQ.isLoading;

  // ── Plan 187 — selección múltiple y acciones en lote ─────────────────────────
  const qc = useQueryClient();
  const bulkEnabled = useBulkActionsEnabled();
  const [bulkToast, setBulkToast] = useState<ToastState | null>(null);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const runnerRef = useRef(createBulkRunner());
  const headerWrapRef = useRef<HTMLSpanElement>(null);
  const bulkRunning = bulkProgress !== null;
  const visibleIds = useMemo(() => items.map((i) => i.id), [items]);
  const sel = useRowSelection({
    visibleIds,
    enabled: bulkEnabled,
    escapeDisabled: detailId !== null || bulkRunning,
  });

  // Auto-ocultado del Toast agregado (8 s, con cleanup).
  useEffect(() => {
    if (!bulkToast) return;
    const t = setTimeout(() => setBulkToast(null), 8000);
    return () => clearTimeout(t);
  }, [bulkToast]);

  // Tri-estado de la cabecera (propiedad del DOM, NO estilo — Checkbox sin forwardRef).
  useEffect(() => {
    const el = headerWrapRef.current?.querySelector("input");
    if (el) el.indeterminate = sel.header === "some";
  }, [sel.header]);

  async function runBulkDelete() {
    const ids = sel.orderedSelectedIds;
    const p = runnerRef.current.run(
      ids,
      async (id) => {
        await Executions.deleteOne(id);
      },
      (done, total) => setBulkProgress({ done, total }),
    );
    if (!p) return;
    setBulkProgress({ done: 0, total: ids.length });
    const result = await p;
    setBulkProgress(null);
    setBulkToast(summarizeBulk(result, "ejecución borrada", "ejecuciones borradas"));
    sel.retainFailed(result.failed.map((f) => f.id)); // C1: retención funcional
    await qc.invalidateQueries({ queryKey: ["execution-history"] });
  }

  async function copySelectedLinks() {
    // Deep-link con receptor REAL (?exec=<id> abre el drawer, 165 F3). Clave canónica
    // "exec" (197 §8.7 c) construida sobre la URL REAL de la página (C4) — nunca
    // hardcodear la ruta. copyText del copyService (194) con fallback LAN — sin
    // navigator.clipboard.writeText inline (ratchet de copia).
    const text = sel.orderedSelectedIds
      .map((id) => {
        const u = new URL(window.location.href);
        u.searchParams.set("exec", String(id));
        return u.toString();
      })
      .join("\n");
    const res = await copyText(text);
    setBulkToast(
      res.ok
        ? { variant: "success", body: `${sel.count} links copiados` }
        : {
            variant: "error",
            title: "No se pudo copiar",
            body: "El portapapeles no está disponible en este contexto.",
          },
    );
  }

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

        {/* Plan 269 F4 — filtro por nivel de veredicto. Es de PRESENTACION: se
            aplica en cliente sobre lo que el servidor ya trajo.
            Usa la primitiva Select de components/ui, nunca el tag crudo: el
            ratchet de deuda de formularios cuenta los tags crudos por archivo y
            este archivo ya tiene su cupo lleno en 4 (medido: agregar uno crudo lo
            subia a 5 y ponia el ratchet rojo con deuda PROPIA). Ojo: ese ratchet
            cuenta por texto, asi que este comentario tampoco puede nombrar el tag
            con su sintaxis literal. */}
        <Select
          className={styles.filterSelect}
          value={filters.verdict_level ?? ""}
          onChange={(e) => setFilter("verdict_level", e.target.value)}
          aria-label="Filtrar por veredicto"
        >
          {VERDICT_LEVEL_FILTERS.map((v) => (
            <option key={v.value} value={v.value}>{v.label}</option>
          ))}
        </Select>

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
        {/* Plan 173 F3 — guardar estos filtros con nombre y volver de un click.
            `limit`/`offset` JAMÁS entran a un preset: son paginación, no filtro. */}
        <SavedViewsBar
          screenId="history"
          currentFilters={normalizeFilters({
            agent_type: filters.agent_type,
            runtime: filters.runtime,
            status: filters.status,
            days: filters.days,
          })}
          onApply={(f) =>
            setFilters((prev) => ({
              ...prev,
              agent_type: f.agent_type ?? "",
              runtime: f.runtime ?? "",
              status: f.status ?? "",
              days: f.days ?? "",
              // Aplicar un preset siempre vuelve a la primera página: quedarse en
              // la 5 de un filtro que ya no existe muestra una tabla vacía.
              offset: 0,
            }))
          }
          // Plan 173 F6 — solo se restaura si NADA más restauró los filtros.
          defaultFilters={{
            agent_type: DEFAULT_FILTERS.agent_type,
            runtime: DEFAULT_FILTERS.runtime,
            status: DEFAULT_FILTERS.status,
            days: DEFAULT_FILTERS.days,
          }}
          urlFilterKeys={["agent_type", "runtime", "status", "verdict_level", "days"]}
        />
        {/* Plan 173 F4 — qué columnas ve este operador. */}
        <TableColumnsMenu
          columns={HISTORY_COLUMNS}
          prefs={tablePrefs}
          onChange={cambiarPrefs}
        />
      </div>

      {/* Plan 194 F4.b — Copiar tabla como CSV / Markdown / Tabla (ADO) */}
      {items.length > 0 && (
        <CopyAsButton
          options={[
            {
              label: "CSV",
              build: () => {
                const r = executionHistoryToRows(items);
                return rowsToCsv(r.headers, r.csvRows);
              },
              successBody: () => `Tabla copiada como CSV (${copiedRowsLabel(items.length)}).`,
            },
            {
              label: "Markdown",
              build: () => {
                const r = executionHistoryToRows(items);
                return rowsToMarkdownTable(r.headers, r.mdRows);
              },
              successBody: () => `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}).`,
            },
            {
              label: "Tabla (ADO)",
              build: () => {
                const r = executionHistoryToRows(items);
                return rowsToMarkdownTable(r.headers, r.mdRows);
              },
              buildHtml: () => {
                const r = executionHistoryToRows(items);
                return rowsToHtmlTable(r.headers, r.mdRows);
              },
              successBody: (m) =>
                m === "richClipboard"
                  ? `Tabla copiada para ADO (${copiedRowsLabel(items.length)}).`
                  : `Tabla copiada como Markdown (${copiedRowsLabel(items.length)}; sin copia enriquecida en este contexto).`,
            },
          ]}
        />
      )}

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
                {bulkEnabled && (
                  <th className={styles.selectCell}>
                    <span ref={headerWrapRef}>
                      <Checkbox
                        label=""
                        aria-label="Seleccionar todo lo visible"
                        checked={sel.header === "all"}
                        onChange={() => {}}
                        onClick={(e) => {
                          e.stopPropagation();
                          sel.onToggleAll();
                        }}
                      />
                    </span>
                  </th>
                )}
                {isColVisible(tablePrefs, "inicio") && (
                  <th data-col="inicio" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "inicio", HISTORY_COLUMNS))}>
                    Inicio{sortMarca("inicio")}
                  </th>
                )}
                {isColVisible(tablePrefs, "agente") && (
                  <th data-col="agente" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "agente", HISTORY_COLUMNS))}>
                    Agente{sortMarca("agente")}
                  </th>
                )}
                {isColVisible(tablePrefs, "runtime") && (
                  <th data-col="runtime" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "runtime", HISTORY_COLUMNS))}>
                    Runtime{sortMarca("runtime")}
                  </th>
                )}
                {isColVisible(tablePrefs, "modelo") && (
                  <th data-col="modelo" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "modelo", HISTORY_COLUMNS))}>
                    Modelo{sortMarca("modelo")}
                  </th>
                )}
                {isColVisible(tablePrefs, "estado") && (
                  <th data-col="estado" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "estado", HISTORY_COLUMNS))}>
                    Estado{sortMarca("estado")}
                  </th>
                )}
                {/* Plan 269 F4 — sin onClick de sort y sin sortMarca A PROPOSITO:
                    `veredicto` no tiene sortKey, y ofrecer un orden que el backend
                    no puede dar seria prometer algo falso. */}
                {isColVisible(tablePrefs, "veredicto") && (
                  <th data-col="veredicto">Veredicto</th>
                )}
                {isColVisible(tablePrefs, "duracion") && (
                  <th data-col="duracion" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "duracion", HISTORY_COLUMNS))}>
                    Duración{sortMarca("duracion")}
                  </th>
                )}
                {isColVisible(tablePrefs, "costo") && (
                  <th data-col="costo" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "costo", HISTORY_COLUMNS))}>
                    Costo{sortMarca("costo")}
                  </th>
                )}
                {isColVisible(tablePrefs, "prompt") && (
                  <th data-col="prompt" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "prompt", HISTORY_COLUMNS))}>
                    Prompt{sortMarca("prompt")}
                  </th>
                )}
                {isColVisible(tablePrefs, "archivos") && (
                  <th data-col="archivos" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "archivos", HISTORY_COLUMNS))}>
                    Archivos{sortMarca("archivos")}
                  </th>
                )}
                {isColVisible(tablePrefs, "ticket") && (
                  <th data-col="ticket" onClick={() => cambiarPrefs(cycleSort(tablePrefs, "ticket", HISTORY_COLUMNS))}>
                    Ticket{sortMarca("ticket")}
                  </th>
                )}
                {/* Plan 175 F4 — acciones rápidas al hover. Solo las seguras:
                    el registro las filtra con doble cerrojo (quick Y safe). */}
                {ctxMenuEnabled && <th aria-label="Acciones rápidas" />}
              </tr>
            </thead>
            {/* Plan 172 F4 — recorrer con j/k o flechas y abrir con Enter, sin mouse. */}
            <tbody {...roving.containerProps}>
              {items.map((item, idx) => (
                <tr
                  key={item.id}
                  className={styles.row}
                  onClick={() => setDetailId(item.id)}
                  title={withShortcutHint(
                    "Click para ver detalle",
                    "Enter abre · j/k navega",
                    isUiShortcutsEnabled(),
                  )}
                  {...combinarProps(
                    combinarProps(roving.rowProps(idx), getPrefetchProps(item.id)),
                    combinarProps(
                      ctxMenu.rowProps(actionsForExecution(item, window.location.origin)),
                      peekEnabled
                        ? {
                            onMouseEnter: (ev: React.MouseEvent) =>
                              peek.hoverStart(
                                { kind: "execution", id: item.id },
                                (ev.currentTarget as HTMLElement).getBoundingClientRect(),
                              ),
                            onMouseLeave: () => peek.hoverEnd(),
                          }
                        : {},
                    ),
                  )}
                >
                  {bulkEnabled && (
                    <td className={styles.selectCell}>
                      <Checkbox
                        label=""
                        aria-label={`Seleccionar ejecución #${item.id}`}
                        checked={sel.isRowSelected(item.id)}
                        onChange={() => {}}
                        onClick={(e) => sel.onRowCheckboxClick(item.id, e)}
                      />
                    </td>
                  )}
                  {isColVisible(tablePrefs, "inicio") && (
                  <td className={styles.dateCell}>{formatRelativeTime(item.started_at)}</td>
                  )}
                  {isColVisible(tablePrefs, "agente") && (
                  <td>{item.agent_type}</td>
                  )}
                  {isColVisible(tablePrefs, "runtime") && (
                  <td className={styles.mono}>{item.runtime ?? "—"}</td>
                  )}
                  {isColVisible(tablePrefs, "modelo") && (
                  <td className={styles.mono}>{item.model ?? "—"}</td>
                  )}
                  {isColVisible(tablePrefs, "estado") && (
                  <td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>
                  )}
                  {isColVisible(tablePrefs, "veredicto") && (
                  <td>
                    {(() => {
                      // run_verdict, NO verdict: `verdict` ya existe y guarda la
                      // revision humana (models.py:255).
                      const v = describeVerdict(item.run_verdict);
                      // Un run en curso no trae veredicto, asi que la celda queda
                      // vacia en vez de decir "Con advertencias".
                      if (!v) return null;
                      return (
                        <StatusChip tone={verdictChipTone(v.tone)} size="sm" title={v.detail}>
                          {v.label}
                        </StatusChip>
                      );
                    })()}
                  </td>
                  )}
                  {isColVisible(tablePrefs, "duracion") && (
                  <td className={styles.numCell}>{formatDuration(item.duration_ms)}</td>
                  )}
                  {isColVisible(tablePrefs, "costo") && (
                  <td className={styles.numCell}>{formatCostUsd(item.cost_usd)}</td>
                  )}
                  {isColVisible(tablePrefs, "prompt") && (
                    <td className={styles.mono}>
                      {item.prompt_sha
                        ? <span title={item.prompt_sha}>{item.prompt_sha.slice(0, 7)}</span>
                        : "—"}
                    </td>
                  )}
                  {isColVisible(tablePrefs, "archivos") && (
                  <td className={styles.numCell}>{item.produced_files_count}</td>
                  )}
                  {isColVisible(tablePrefs, "ticket") && (
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
                  )}
                  {ctxMenuEnabled && (
                    <td className={styles.actionsCell}>
                      {/* stopPropagation: clickear un icono no puede abrir el drawer. */}
                      <span className={styles.rowActions} onClick={(e) => e.stopPropagation()}>
                        {quickActions(actionsForExecution(item, window.location.origin)).map((a) => (
                          <IconButton
                            key={a.id}
                            size="sm"
                            label={a.label}
                            icon={copiedId === `${a.id}-${item.id}` ? "✓" : a.icon}
                            onClick={() =>
                              void a.run({
                                ...accionCtx,
                                onDone: (id, ok) => marcarHecho(id, item.id, ok),
                              })
                            }
                          />
                        ))}
                      </span>
                    </td>
                  )}
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

      {/* Plan 187 — barra flotante de acciones en lote + Toast agregado */}
      {bulkEnabled && (
        <BulkActionsBar
          count={sel.count}
          running={bulkRunning}
          progress={bulkProgress}
          onClear={sel.clear}
          actions={[
            {
              id: "copy-links",
              destructive: false,
              label: (n) => `Copiar ${n} links`,
              run: () => void copySelectedLinks(),
            },
            {
              id: "delete-selected",
              destructive: true,
              label: (n) => `Borrar ${n}`,
              armedLabel: (n) => `¿Borrar ${n}? Confirmar`,
              run: () => void runBulkDelete(),
            },
          ]}
        />
      )}
      {bulkToast && <Toast toast={bulkToast} onClose={() => setBulkToast(null)} />}

      {/* Drawer de detalle (Plan 38 C2) */}
      {/* Plan 175 F2/F3 — la vista previa y el menú viven fuera de la tabla
          (portal), así que no pueden romper su layout ni su scroll. */}
      <PeekCard
        state={peek.state}
        content={
          peek.state.target
            ? (() => {
                const it = items.find((i) => i.id === peek.state.target?.id);
                return it ? buildExecutionPeek(it) : null;
              })()
            : null
        }
        anchorRect={peek.anchorRect}
        onCardHover={peek.cardHover}
        onCardLeave={peek.cardLeave}
      />
      <ContextMenu
        open={ctxMenu.menu !== null}
        x={ctxMenu.menu?.x ?? 0}
        y={ctxMenu.menu?.y ?? 0}
        actions={ctxMenu.menu?.actions ?? []}
        ctx={accionCtx}
        openedByKeyboard={ctxMenu.menu?.byKeyboard ?? false}
        onClose={ctxMenu.cerrar}
      />

      <ExecutionDetailDrawer
        executionId={detailId}
        onClose={() => setDetailId(null)}
      />
    </div>
  );
}

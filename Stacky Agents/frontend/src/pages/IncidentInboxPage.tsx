/**
 * Bandeja de incidencias abiertas (vista dedicada).
 *
 * Plan 238 F6 la creo como SOLO LECTURA. Detras de la flag
 * STACKY_INCIDENT_INBOX_ACTIONS_ENABLED la bandeja ademas RESUELVE: cerrar la
 * incidencia en el tracker (mismo camino que "Terminar trabajo" del tablero) y
 * lanzar el Dev Resolutor con "Abrir PR" (que al terminar commitea lo que el
 * agente toco y abre el Pull Request), de a una o en lote.
 *
 * Toda la logica de decision vive en incidents/incidentInboxModel y
 * incidents/incidentInboxActionsModel (puros y testeados): esta capa solo
 * renderiza y cablea. Las mutaciones NO tienen endpoints propios: reusan
 * /api/tickets/<id>/finish-work y /api/agents/run-incident-dev, para que la
 * bandeja y el tablero nunca discrepen.
 *
 * Cero estilos en linea y cero colores literales aca (los exigen los ratchets
 * de deuda de interfaz); el color por tipo viaja por una variable CSS, y los
 * controles salen del barrel de primitivas (ratchet de formularios).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IncidentInbox, HarnessFlags, Incidents, Tickets } from "../api/endpoints";
import {
  filterBySearch,
  sortIncidents,
  summaryLabel,
  countByState,
  formatIncidentsForCopy,
  parseScope,
  isProviderBlind,
  type IncidentScope,
  type IncidentInboxItem,
} from "../incidents/incidentInboxModel";
import { describeVerdict } from "../utils/runVerdict";
import {
  DIVERGENCE_BADGE_LABEL,
  DIVERGENCE_BADGE_TITLE,
  filterDiverged,
  formatDivergenceCount,
  isDiverged,
  resolveDivergenceBadgeEnabled,
  resolveDivergenceCount,
} from "../incidents/incidentDivergence";
import {
  BULK_FINISH_REASON,
  DEFAULT_FINISH_STATE,
  FINISH_STATE_SUGGESTIONS,
  canFinishIncident,
  canResolveIncident,
  normalizeFinishState,
  partitionSelection,
  resolveInboxActionsEnabled,
  skippedNotice,
} from "../incidents/incidentInboxActionsModel";
import {
  DEFAULT_OPEN_PR,
  describeOpenPrControl,
  PREFLIGHT_CAIDO,
} from "../incidents/incidentDevPrModel";
import {
  copyText,
  resolveCopyExportEnabled,
  COPY_TOAST_SUCCESS,
  COPY_TOAST_ERROR,
} from "../services/copyService";
import {
  INCIDENT_ICON,
  getWorkItemTypeColor,
  formatWorkItemTypeLabel,
} from "../utils/workItemTypeColor";
import { useBulkActionsEnabled } from "../services/bulkFlags";
import {
  capExecutionBatch,
  createBulkRunner,
  summarizeBulk,
  type BulkWorker,
} from "../services/bulkModel";
import { useWorkbench } from "../store/workbench";
import EmptyState from "../components/EmptyState";
import LoadErrorState from "../components/LoadErrorState";
import SkeletonList from "../components/SkeletonList";
import Toast, { type ToastState } from "../components/Toast";
import FinishWorkButton from "../components/FinishWorkButton";
import BulkActionsBar from "../components/bulk/BulkActionsBar";
import { useRowSelection } from "../components/bulk/useRowSelection";
import { Button, Checkbox, Input } from "../components/ui";
import type { Ticket } from "../types";
import styles from "./IncidentInboxPage.module.css";

const AYUDA_FLAG_OFF =
  "La bandeja de incidencias esta apagada. Activala en Configuracion > Flags del arnes > Interfaz UI > 'Bandeja de incidencias abiertas'.";

/** Ticket minimo para FinishWorkButton (solo usa id / ado_id / title / estado). */
function ticketShim(item: IncidentInboxItem): Ticket {
  return {
    id: item.id,
    ado_id: item.ado_id,
    project: "",
    title: item.title,
    ado_state: item.ado_state,
    ado_url: item.ado_url,
    work_item_type: item.work_item_type,
    assigned_to_ado: item.assigned_to_ado,
    stacky_status: item.stacky_status as Ticket["stacky_status"],
  };
}

/** Punto de color por tipo de item: el color se aplica con setProperty sobre una
 *  variable CSS, nunca con estilos en linea (lo exige el ratchet de interfaz). */
function TypeDot({ workItemType }: { workItemType?: string }) {
  const ref = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    ref.current?.style.setProperty("--incident-type-color", getWorkItemTypeColor(workItemType));
  }, [workItemType]);
  return (
    <span
      ref={ref}
      className={styles.typeDot}
      title={formatWorkItemTypeLabel(workItemType)}
      aria-label={formatWorkItemTypeLabel(workItemType)}
    />
  );
}

export default function IncidentInboxPage() {
  const qc = useQueryClient();
  const [scope, setScope] = useState<IncidentScope>(() =>
    parseScope(new URLSearchParams(window.location.search).get("scope")),
  );
  const [search, setSearch] = useState("");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [finishState, setFinishState] = useState(DEFAULT_FINISH_STATE);
  const [openPr, setOpenPr] = useState(DEFAULT_OPEN_PR);
  const [busyRowId, setBusyRowId] = useState<number | null>(null);
  // Plan 270 F5 — filtro del chip "Sin sincronizar". Solo lectura: no escribe nada.
  const [soloDivergentes, setSoloDivergentes] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const runnerRef = useRef(createBulkRunner());
  const headerWrapRef = useRef<HTMLSpanElement>(null);
  const bulkRunning = bulkProgress !== null;

  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const agentRuntime = useWorkbench((s) => s.agentRuntime);

  const statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });

  const itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, scope],
    queryFn: () => IncidentInbox.items(activeProjectName, scope),
    enabled: statusQ.data?.data?.enabled === true,
    refetchInterval: 45_000,
    staleTime: 22_500,
    refetchOnWindowFocus: true,
  });

  // Gate del portapapeles (plan 194): mismo patron que components/CopyAsButton.
  const flagsQ = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
    staleTime: 60_000,
  });
  const copiarHabilitado = resolveCopyExportEnabled(flagsQ.data?.flags);

  // ── Acciones (cerrar / resolver+PR / lote) ─────────────────────────────────
  const actionsEnabled = resolveInboxActionsEnabled(statusQ.data?.data);
  const bulkEnabled = useBulkActionsEnabled();
  const selectionEnabled = actionsEnabled && bulkEnabled;

  // Gates del Dev Resolutor y del auto-PR: fuente unica /api/incidents/status,
  // la MISMA que consume el tablero. Solo se pide si la bandeja puede escribir.
  const incidentsStatusQ = useQuery({
    queryKey: ["incidents-status"],
    queryFn: () => Incidents.status(),
    enabled: actionsEnabled,
    staleTime: 5 * 60 * 1000,
  });
  const devResolverEnabled = Boolean(incidentsStatusQ.data?.dev_resolver_enabled);
  const devPrEnabled = Boolean(incidentsStatusQ.data?.dev_pr_enabled);
  const puedeResolverAlgo = actionsEnabled && devResolverEnabled;
  // 2026-08-02 — chequeo PREVIO de repositorio git, igual que en el tablero: el
  // tilde no se esconde cuando el PR no puede salir, se deshabilita CON motivo.
  const prPreflightQ = useQuery({
    queryKey: ["dev-pr-preflight", activeProjectName],
    queryFn: () => Incidents.devPrPreflight(activeProjectName),
    enabled: puedeResolverAlgo && devPrEnabled,
    staleTime: 60 * 1000,
  });
  const prControl = describeOpenPrControl({
    canResolve: puedeResolverAlgo,
    devPrEnabled,
    preflight: prPreflightQ.data ?? (prPreflightQ.isError ? PREFLIGHT_CAIDO : null),
    deseado: openPr,
  });
  const showOpenPr = prControl.visible;

  const dto = itemsQ.data?.data ?? null;
  const raw = useMemo(() => dto?.items ?? [], [dto]);
  const counts = dto?.counts ?? { open: 0, closed: 0, total: 0 };
  const visible = useMemo(() => sortIncidents(filterBySearch(raw, search)), [raw, search]);
  const byState = useMemo(() => countByState(visible), [visible]);
  const closedStates = useMemo(
    () => dto?.closed_states ?? statusQ.data?.data?.closed_states ?? [],
    [dto, statusQ.data],
  );

  // Plan 270 F5 — el gate del badge/chip y la lista realmente MOSTRADA.
  const divergenciaVisible = resolveDivergenceBadgeEnabled(statusQ.data?.data);
  // C7 — el filtro se aplica ACA, no dentro del .map: `visible` alimenta tambien
  // a visibleIds -> useRowSelection -> "Seleccionar todo" -> cierre en LOTE, que
  // ESCRIBE en el tracker. Si el filtro viviera solo en el .map, "Seleccionar
  // todo" marcaria filas ocultas y el lote escribiria sobre incidencias que el
  // operador nunca vio.
  const mostrados = useMemo(
    () => filterDiverged(visible, soloDivergentes),
    [visible, soloDivergentes],
  );
  // El conteo del SERVIDOR manda; la lista local es el fallback. Se calcula una
  // sola vez y se usa para el gate Y para el texto: si el gate mirara una fuente
  // y el texto otra, el chip podria aparecer vacio. NUNCA sobre `mostrados`: si
  // no, al activar el filtro el numero se congelaria en si mismo.
  const divergentes = resolveDivergenceCount(dto?.diverged_count, visible);
  const textoChip = formatDivergenceCount(divergentes);

  const visibleIds = useMemo(() => mostrados.map((i) => i.id), [mostrados]);
  const sel = useRowSelection({
    visibleIds,
    enabled: selectionEnabled,
    escapeDisabled: bulkRunning,
  });

  // Tri-estado de la cabecera (propiedad del DOM, NO estilo — Checkbox sin forwardRef).
  useEffect(() => {
    const el = headerWrapRef.current?.querySelector("input");
    if (el) el.indeterminate = sel.header === "some";
  }, [sel.header]);

  const refrescar = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["incident-inbox-items", activeProjectName, scope] }),
      qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
      qc.invalidateQueries({ queryKey: ["executions"] }),
    ]);
  }, [qc, activeProjectName, scope]);

  // Cierre de UNA incidencia sin dialogo: es el worker del lote. El boton por
  // fila usa FinishWorkButton (con dry-run y confirmacion en dos pasos).
  const cerrarUna: BulkWorker = useCallback(
    async (ticketId: number) => {
      const r = await Tickets.finishWork(ticketId, {
        operator_reason: BULK_FINISH_REASON,
        publish_to_ado: true,
        target_ado_state: normalizeFinishState(finishState),
        dry_run: false,
        cancel_active_execution: true,
      });
      if (!r.ok) {
        const fallo = r.actions?.find((a) => !a.ok);
        throw new Error(fallo?.reason ?? "el cierre no se completo");
      }
    },
    [finishState],
  );

  // Lanzamiento del Dev Resolutor. Con "Abrir PR" tildado, al terminar el agente
  // el post-hook commitea lo que toco y abre el Pull Request.
  const resolverUna: BulkWorker = useCallback(
    async (ticketId: number) => {
      const r = await Incidents.runDevResolver({
        ticket_id: ticketId,
        runtime: agentRuntime,
        project: activeProjectName,
        // `checked` ya combina el tilde del operador con el chequeo de repo git.
        open_pr: prControl.checked,
      });
      // El backend dice si aceptó el pedido de PR; si no, se avisa en el acto en
      // vez de dejar al operador esperando un PR que nunca va a existir.
      if (r.auto_pr?.requested && !r.auto_pr.accepted) {
        setToast({ variant: "error", body: r.auto_pr.message || "No se pudo pedir el PR automático." });
      }
    },
    [agentRuntime, activeProjectName, prControl.checked],
  );

  const resolverFila = useCallback(
    async (ticketId: number) => {
      setBusyRowId(ticketId);
      try {
        await resolverUna(ticketId);
        setToast({
          variant: "success",
          body: showOpenPr && openPr
            ? "Agente lanzado — al terminar deja el Pull Request abierto"
            : "Agente lanzado sobre la incidencia",
        });
        await refrescar();
      } catch (e) {
        setToast({ variant: "error", body: String((e as Error)?.message ?? e) });
      } finally {
        setBusyRowId(null);
      }
    },
    [resolverUna, refrescar, showOpenPr, openPr],
  );

  const correrLote = useCallback(
    async (kind: "finish" | "resolve") => {
      const predicado = (item: IncidentInboxItem) =>
        kind === "finish"
          ? canFinishIncident({ item, actionsEnabled })
          : canResolveIncident({ item, actionsEnabled, devResolverEnabled, closedStates });

      const { eligible, skipped } = partitionSelection(visible, sel.orderedSelectedIds, predicado);
      const aviso = skippedNotice(skipped);
      if (eligible.length === 0) {
        setToast({
          variant: "warning",
          body: aviso ?? "Ninguna de las seleccionadas admite esta accion.",
        });
        return;
      }
      if (kind === "resolve") {
        // Freno de costo: lanzar agentes cuesta plata de verdad.
        const cap = capExecutionBatch(eligible);
        if (!cap.ok) {
          setToast(cap.toast);
          return;
        }
      }

      const worker = kind === "finish" ? cerrarUna : resolverUna;
      const p = runnerRef.current.run(eligible, worker, (done, total) =>
        setBulkProgress({ done, total }),
      );
      if (!p) return; // guard: ya hay un lote corriendo
      setBulkProgress({ done: 0, total: eligible.length });
      const result = await p;
      setBulkProgress(null);

      const resumen =
        kind === "finish"
          ? summarizeBulk(result, "incidencia cerrada", "incidencias cerradas")
          : summarizeBulk(result, "agente lanzado", "agentes lanzados");
      setToast(aviso ? { ...resumen, body: `${resumen.body} · ${aviso}` } : resumen);
      sel.retainFailed(result.failed.map((f) => f.id));
      await refrescar();
    },
    [visible, sel, actionsEnabled, devResolverEnabled, closedStates, cerrarUna, resolverUna, refrescar],
  );

  const cambiarScope = (next: IncidentScope) => {
    setScope(next);
    // parseRoute preserva los parametros desconocidos verbatim (plan 165) y
    // replaceState NO dispara popstate, asi que la pagina no se re-monta.
    const url = new URL(window.location.href);
    if (next === "all") url.searchParams.set("scope", "todas");
    else url.searchParams.delete("scope");
    window.history.replaceState({}, "", url.pathname + url.search);
  };

  const copiarLista = async () => {
    const r = await copyText(formatIncidentsForCopy(visible));
    setToast({ variant: r.ok ? "success" : "error", body: r.ok ? COPY_TOAST_SUCCESS : COPY_TOAST_ERROR });
  };

  // 1) cargando
  if (statusQ.isLoading || (statusQ.data?.data?.enabled === true && itemsQ.isLoading)) {
    return <SkeletonList />;
  }

  // 2) la funcion esta apagada / 3) el servidor la reporta apagada
  const apagadaPorFlag = statusQ.data?.data?.enabled === false;
  const apagadaPorServidor =
    itemsQ.data?.ok === false && itemsQ.data?.errorBody?.error === "feature_disabled";
  if (apagadaPorFlag || apagadaPorServidor) {
    return <EmptyState variant="generic" title="Bandeja de incidencias apagada" message={AYUDA_FLAG_OFF} />;
  }

  // 4) error de lectura
  if (itemsQ.isError || itemsQ.data?.ok === false) {
    return (
      <LoadErrorState
        what="las incidencias"
        error={itemsQ.data?.errorBody?.message ?? itemsQ.error}
        onRetry={() => void itemsQ.refetch()}
      />
    );
  }

  const cabecera = (
    <div className={styles.header}>
      <div className={styles.headerLeft}>
        <h1 className={styles.title}>
          {INCIDENT_ICON} Incidencias
        </h1>
        <span className={styles.count}>{summaryLabel(counts)}</span>
      </div>
      <div className={styles.headerActions}>
        <div className={styles.scopeToggle} role="group" aria-label="Alcance">
          <button
            type="button"
            className={`${styles.scopeBtn} ${scope === "open" ? styles.scopeActive : ""}`}
            onClick={() => cambiarScope("open")}
          >
            Solo abiertas
          </button>
          <button
            type="button"
            className={`${styles.scopeBtn} ${scope === "all" ? styles.scopeActive : ""}`}
            onClick={() => cambiarScope("all")}
          >
            Todas
          </button>
        </div>
        <div className={styles.search}>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por titulo, numero o estado"
            aria-label="Buscar incidencias"
          />
        </div>
        {actionsEnabled && (
          <div className={styles.finishStateBox}>
            <label className={styles.finishStateLabel} htmlFor="inbox-finish-state">
              Estado al cerrar en lote
            </label>
            <Input
              id="inbox-finish-state"
              className={styles.finishStateInput}
              value={finishState}
              onChange={(e) => setFinishState(e.target.value)}
              placeholder={DEFAULT_FINISH_STATE}
              list="inbox-finish-state-options"
              disabled={bulkRunning}
            />
            <datalist id="inbox-finish-state-options">
              {FINISH_STATE_SUGGESTIONS.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </div>
        )}
        {prControl.visible && (
          <Checkbox
            label={`${prControl.etiqueta} al resolver`}
            labelClassName={styles.inlineToggle}
            checked={prControl.checked}
            onChange={(e) => setOpenPr(e.target.checked)}
            disabled={bulkRunning || prControl.disabled}
            title={prControl.motivo || "Al terminar el agente, commitea lo que toco y abre el Pull Request"}
          />
        )}
        {prControl.visible && prControl.motivo && (
          <span className={styles.inlineToggle} title={prControl.motivo}>
            {prControl.disabled ? "⚠ " : "ℹ "}
            {prControl.motivo}
          </span>
        )}
        {copiarHabilitado && (
          <Button variant="ghost" size="sm" className={styles.copyBtn} onClick={() => void copiarLista()}>
            Copiar lista
          </Button>
        )}
      </div>
    </div>
  );

  // 5a) el tracker no sincroniza el tipo de item: nunca una pantalla vacia mentirosa
  if (isProviderBlind(dto)) {
    return (
      <div className={styles.root}>
        {cabecera}
        <EmptyState
          variant="generic"
          title="No se puede separar las incidencias en este proyecto"
          message={`Este proyecto tiene ${dto?.untyped_count ?? 0} ticket(s) sin tipo de item sincronizado, asi que la bandeja no puede separarlos. Suele pasar cuando el tracker no expone el tipo de item. Las incidencias siguen visibles en el tablero general.`}
        />
      </div>
    );
  }

  // 5b) vacio honesto
  if (visible.length === 0) {
    return (
      <div className={styles.root}>
        {cabecera}
        <EmptyState
          variant="generic"
          title={scope === "open" ? "No hay incidencias abiertas" : "Sin incidencias"}
          message={
            scope === "open"
              ? "No hay incidencias abiertas en este proyecto."
              : "Este proyecto no tiene incidencias."
          }
        />
      </div>
    );
  }

  // 6) caso feliz
  return (
    <div className={styles.root}>
      {cabecera}
      {dto?.truncated && (
        <p className={styles.banner}>
          Mostrando las primeras 1000 incidencias. Afina la busqueda para ver el resto.
        </p>
      )}
      <div className={styles.chips}>
        {selectionEnabled && (
          <span ref={headerWrapRef} className={styles.selectAll}>
            <Checkbox
              label="Seleccionar todo"
              labelClassName={styles.inlineToggle}
              checked={sel.header === "all"}
              onChange={() => {}}
              onClick={(e) => {
                e.stopPropagation();
                sel.onToggleAll();
              }}
              disabled={bulkRunning}
            />
          </span>
        )}
        {byState.map((s) => (
          <span key={s.state} className={styles.chip}>
            {s.state} {s.count}
          </span>
        ))}
        {divergenciaVisible && textoChip !== "" && (
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={soloDivergentes}
            title={DIVERGENCE_BADGE_TITLE}
            onClick={() => setSoloDivergentes((v) => !v)}
          >
            {textoChip}
          </Button>
        )}
      </div>
      <div className={styles.list}>
        {mostrados.map((item: IncidentInboxItem) => {
          const puedeCerrar = canFinishIncident({ item, actionsEnabled });
          const puedeResolver = canResolveIncident({
            item,
            actionsEnabled,
            devResolverEnabled,
            closedStates,
          });
          const corriendo = item.stacky_status === "running";
          return (
            <div key={item.id} className={styles.row}>
              {selectionEnabled && (
                <Checkbox
                  label=""
                  labelClassName={styles.selectCell}
                  aria-label={`Seleccionar la incidencia #${item.ado_id}`}
                  checked={sel.isRowSelected(item.id)}
                  onChange={() => {}}
                  onClick={(e) => sel.onRowCheckboxClick(item.id, e)}
                  disabled={bulkRunning}
                />
              )}
              <TypeDot workItemType={item.work_item_type} />
              <span className={styles.adoId}>#{item.ado_id}</span>
              <span className={styles.rowTitle}>{item.title}</span>
              {item.ado_state && <span className={styles.stateBadge}>{item.ado_state}</span>}
              <span className={item.is_open ? styles.openBadge : styles.closedBadge}>
                {item.is_open ? "Abierta" : "Cerrada"}
              </span>
              {divergenciaVisible && isDiverged(item) && (
                <span className={styles.divergedBadge} title={DIVERGENCE_BADGE_TITLE}>
                  {DIVERGENCE_BADGE_LABEL}
                </span>
              )}
              {/* Plan 269 F5 — veredicto de la ultima corrida. run_verdict, NO
                  verdict. Sin veredicto (o sin ejecuciones) no se dibuja nada. */}
              {(() => {
                const v = describeVerdict(item.run_verdict);
                return v ? (
                  <span className={styles.verdictBadge} data-tone={v.tone} title={v.detail}>
                    {v.label}
                  </span>
                ) : null;
              })()}
              {corriendo && <span className={styles.runningDot}>agente corriendo</span>}
              <span className={styles.assignee}>{item.assigned_to_ado ?? "sin asignar"}</span>
              <span className={styles.rowActions}>
                {puedeResolver && (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busyRowId === item.id || bulkRunning}
                    onClick={() => void resolverFila(item.id)}
                    title={
                      showOpenPr && openPr
                        ? "Resolver con un agente y dejar el Pull Request abierto"
                        : "Resolver esta incidencia con un agente dev"
                    }
                  >
                    {busyRowId === item.id ? "⏳ Lanzando…" : "🔧 Resolver"}
                  </Button>
                )}
                {puedeCerrar && (
                  <FinishWorkButton
                    ticket={ticketShim(item)}
                    disabled={corriendo || bulkRunning}
                    onCompleted={() => void refrescar()}
                  />
                )}
                {item.ado_url && (
                  <a className={styles.link} href={item.ado_url} target="_blank" rel="noopener noreferrer">
                    Abrir en el tracker
                  </a>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {selectionEnabled && (
        <BulkActionsBar
          count={sel.count}
          running={bulkRunning}
          progress={bulkProgress}
          onClear={sel.clear}
          actions={[
            {
              id: "finish-selected",
              destructive: true,
              label: (n) => `Cerrar ${n} en ${normalizeFinishState(finishState)}`,
              armedLabel: (n) => `¿Cerrar ${n}? Confirmar`,
              run: () => void correrLote("finish"),
            },
            {
              id: "resolve-selected",
              destructive: true,
              label: (n) => (showOpenPr && openPr ? `Resolver ${n} + PR` : `Resolver ${n}`),
              armedLabel: (n) => `¿Lanzar ${n} agentes? Confirmar`,
              run: () => void correrLote("resolve"),
            },
          ]}
        />
      )}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

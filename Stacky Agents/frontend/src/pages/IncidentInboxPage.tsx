/**
 * Plan 238 F6 — Bandeja de incidencias abiertas (vista dedicada, SOLO LECTURA).
 * Muestra unicamente incidencias (Issue/Bug) con las abiertas primero. No cierra,
 * no reasigna, no publica y no lanza agentes: eso sigue viviendo en el tablero.
 * Toda la logica esta en incidents/incidentInboxModel (puro y testeado): esta capa
 * solo renderiza. Cero estilos en linea y cero colores literales aca (los exigen
 * los ratchets de deuda de interfaz); el color por tipo viaja por una variable CSS.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { IncidentInbox, HarnessFlags } from "../api/endpoints";
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
import { useWorkbench } from "../store/workbench";
import EmptyState from "../components/EmptyState";
import LoadErrorState from "../components/LoadErrorState";
import SkeletonList from "../components/SkeletonList";
import Toast, { type ToastState } from "../components/Toast";
import { Button, Input } from "../components/ui";
import styles from "./IncidentInboxPage.module.css";

const AYUDA_FLAG_OFF =
  "La bandeja de incidencias esta apagada. Activala en Configuracion > Flags del arnes > Interfaz UI > 'Bandeja de incidencias abiertas'.";

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
  const [scope, setScope] = useState<IncidentScope>(() =>
    parseScope(new URLSearchParams(window.location.search).get("scope")),
  );
  const [search, setSearch] = useState("");
  const [toast, setToast] = useState<ToastState | null>(null);

  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

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

  const dto = itemsQ.data?.data ?? null;
  const raw = useMemo(() => dto?.items ?? [], [dto]);
  const counts = dto?.counts ?? { open: 0, closed: 0, total: 0 };
  const visible = useMemo(() => sortIncidents(filterBySearch(raw, search)), [raw, search]);
  const byState = useMemo(() => countByState(visible), [visible]);

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
          message={`Este proyecto tiene ${dto?.untyped_count ?? 0} ticket(s) sin tipo de item sincronizado, asi que la bandeja no puede separarlos. Suele pasar cuando el tracker no es Azure DevOps. Las incidencias siguen visibles en el tablero general.`}
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
        {byState.map((s) => (
          <span key={s.state} className={styles.chip}>
            {s.state} {s.count}
          </span>
        ))}
      </div>
      <div className={styles.list}>
        {visible.map((item: IncidentInboxItem) => (
          <div key={item.id} className={styles.row}>
            <TypeDot workItemType={item.work_item_type} />
            <span className={styles.adoId}>#{item.ado_id}</span>
            <span className={styles.rowTitle}>{item.title}</span>
            {item.ado_state && <span className={styles.stateBadge}>{item.ado_state}</span>}
            <span className={item.is_open ? styles.openBadge : styles.closedBadge}>
              {item.is_open ? "Abierta" : "Cerrada"}
            </span>
            {item.stacky_status === "running" && (
              <span className={styles.runningDot}>agente corriendo</span>
            )}
            <span className={styles.assignee}>{item.assigned_to_ado ?? "sin asignar"}</span>
            {item.ado_url && (
              <a className={styles.link} href={item.ado_url} target="_blank" rel="noopener noreferrer">
                Abrir en el tracker
              </a>
            )}
          </div>
        ))}
      </div>
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

import React, { useState, useCallback, useMemo, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, FlowConfig, Executions, Memory, Incidents, type StackyMemoryTicketBadge } from "../api/endpoints";
import { MEMORY_ADVANCED_ENABLED } from "../config/featureFlags";
import type { Ticket, TicketNode, TicketHierarchy, AgentExecution, VsCodeAgent } from "../types";
import AgentRuntimeSelector from "../components/AgentRuntimeSelector";
import ModelEffortPicker from "../components/ModelEffortPicker";
import { useRovingFocus } from "../hooks/useRovingFocus";
import { useModelCatalog } from "../hooks/useModelCatalog";
import AvisoCatalogoModelos from "../components/AvisoCatalogoModelos";  // Plan 288 F9
import { useModelPickerEnabled } from "../hooks/useModelPickerEnabled";
import { useTicketSync, DEFAULT_INTERVAL_MS as TICKET_SYNC_INTERVAL_MS } from "../hooks/useTicketSync";
// Plan 295 F10 — el import de DEFAULT_INTERVAL_MS SE CONSERVA: es el fallback si el
// endpoint de config no responde. Borrarlo convertiria un fallo de ese endpoint en
// un tablero sin auto-sync.
import { intervaloDeSync } from "./ticketSyncIntervalo";
import { SyncStatusBar } from "../components/SyncStatusBar";
import IntegrationHealthBanner from "../components/IntegrationHealthBanner";
import TicketGraphView from "../components/TicketGraphView";
import RecoverExecutionButton from "../components/RecoverExecutionButton";
import Toast, { type ToastState } from "../components/Toast";
import { useConfirm, Dialog } from "../components/ui";
import FinishWorkButton from "../components/FinishWorkButton";
import CreateChildTaskButton from "../components/CreateChildTaskButton";
import EpicFromBriefModal from "../components/EpicFromBriefModal";
import TicketLocalInsightButton from "../components/TicketLocalInsightButton";
// Plan 288 F2 — la superficie de clasificación local (JerarquiaLocalControl y
// PublicarEtiquetasGitLab) se retiró de esta vista. El motor de datos sigue vivo:
// columnas, ruta PATCH y contadores de la sincronización. Ver Plan 288 §2.2.
import LoadErrorState from "../components/LoadErrorState";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import IncidentResolverModal from "../components/IncidentResolverModal";
import IncidentInboxEntryButton from "../components/IncidentInboxEntryButton"; // Plan 238
import { Maximize2 } from "lucide-react";                                      // Plan 287 F7
import TicketFullView from "../components/ticket/TicketFullView";              // Plan 287 F6/F7
import { readCachedBoolFlag } from "../services/flagGate";                     // Plan 287 F7
import { parseRoute, serializeRoute } from "../services/routes";               // Plan 287 F7
import { useRunningStatus } from "../hooks/useRunningStatus";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { getAgentType } from "../services/preferences";
import {
  findVsCodeAgent,
  humanizeAgentLaunchError,
  launchAgentWithRuntime,
  launchInProgressLabel,
  openConsoleIfCliRuntime,
  runtimeDisplayLabel,
  runtimeRequiresVsCodeAgent,
} from "../services/agentLaunch";
import { useWorkbench } from "../store/workbench";
// Plan 276 F7 — los rótulos siguen al tracker del proyecto activo, no dicen "ADO" siempre.
import {
  accionAbrirEn, accionSincronizar, nombreDeTracker, refDeTicket,
  tituloDeTickets, trackerEfectivo,
} from "../lib/trackerLabels";
// Plan 282 F6 — el vocabulario de ESTADOS tambien sigue al tracker: en GitLab el
// filtro "Solo abiertos" no filtraba nada y todos los badges caian al mismo gris.
import { colorDeEstado, esEstadoCerrado, sugerenciasDeEstadoCerrado } from "../lib/trackerEstados";
import { canResolveWithAgent } from "../incidents/devResolverModel";
import {
  DEFAULT_OPEN_PR,
  describeOpenPrControl,
  describePrResult,
  debeSeguirConsultando,
  PREFLIGHT_CAIDO,
} from "../incidents/incidentDevPrModel";
import { detectInconsistencyFromRunning } from "../utils/inconsistencyDetector";
import { resolveSuggestedAgent } from "../utils/resolveSuggestedAgent";
import styles from "./TicketBoard.module.css";
import SavedViewsBar from "../components/SavedViewsBar";
import TicketSqlDeployBadge from "../components/TicketSqlDeployBadge";
import { filtersToTicketBoardState, ticketBoardStateToFilters } from "../services/savedViews";
import { actionsForTicket, quickActions } from "../services/entityActions";
import { copyText as copiarTexto } from "../services/clipboard";
import { IconButton } from "../components/ui";
import { formatWorkItemTypeLabel, getWorkItemTypeColor, isIncidentWorkItemType } from "../utils/workItemTypeColor";

// Resuelve el tipo del agente. Prioriza el override explícito que el operador
// fija en EmployeeEditDrawer; cae a heurística sobre el filename si no hay override.
function inferType(filename: string): string {
  const override = getAgentType(filename);
  if (override) return override;
  const f = filename.toLowerCase();
  if (f.includes("business") || f.includes("negocio")) return "business";
  if (f.includes("functional") || f.includes("funcional")) return "functional";
  if (f.includes("technical") || f.includes("tecnic")) return "technical";
  if (f.includes("dev") || f.includes("desarrollador")) return "developer";
  if (f.includes("qa") || f.includes("test")) return "qa";
  return "custom";
}

// Encuentra el filename del agente configurado en el equipo que coincide con el tipo.
// Primero busca en los agentes pinneados (el equipo del operador), luego en todos.
function findAgentFilenameByType(
  agentType: string,
  vsCodeAgents: VsCodeAgent[],
  pinnedFilenames: string[]
): string | null {
  const pinnedMatch = pinnedFilenames.find((f) => inferType(f) === agentType);
  if (pinnedMatch) return pinnedMatch;
  const anyMatch = vsCodeAgents.find((a) => inferType(a.filename) === agentType);
  return anyMatch?.filename ?? null;
}

type ViewMode = "tree" | "graph";



const NEXT_AGENT_LABELS: Record<string, string> = {
  business:   "💼 Negocio",
  functional: "🔍 Funcional",
  technical:  "🔬 Técnico",
  developer:  "🚀 Dev",
  qa:         "✅ QA",
};

function stateColor(state?: string, tracker?: string | null): string {
  if (!state) return "#6b7280";
  return colorDeEstado(state, tracker ?? null);
}

// ─── RunModal ─────────────────────────────────────────────────────────────────

interface RunModalProps {
  ticket: Ticket;
  mode: "suggested" | "custom";
  suggestedLabel: string | null;
  suggestedFilename: string | null;
  vsCodeAgents: VsCodeAgent[];
  isLaunching: boolean;
  errorMessage?: string | null;
  onConfirm: (
    note: string,
    filename: string | null,
    /** Plan 212 F4 — overrides por corrida elegidos en el propio modal. */
    overrides?: { model: string | null; effort: string | null },
  ) => void;
  onClose: () => void;
}

function RunModal({
  ticket,
  mode,
  suggestedLabel,
  suggestedFilename,
  vsCodeAgents,
  isLaunching,
  errorMessage,
  onConfirm,
  onClose,
}: RunModalProps) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  // Plan 282 F4 — tracker del ticket con FALLBACK al del proyecto: el campo
  // `tracker_type` del ticket es OPCIONAL en el payload legacy.
  const tt = trackerEfectivo(
    ticket.tracker_type,
    useWorkbench((s) => s.activeProject?.tracker_type ?? null),
  );
  const [note, setNote] = useState("");
  // Plan 212 F4 — modelo/effort por corrida, elegidos donde se lanza el trabajo.
  const [pickerModel, setPickerModel] = useState<string | null>(null);
  const [pickerEffort, setPickerEffort] = useState<string | null>(null);
  const modelCatalog = useModelCatalog();
  const pickerEnabled = useModelPickerEnabled();
  const [selectedFilename, setSelectedFilename] = useState<string>(vsCodeAgents[0]?.filename ?? "");
  const resolvedFilename = mode === "custom" ? (selectedFilename || null) : suggestedFilename;

  const canConfirm =
    (mode === "suggested" ? !!suggestedLabel : !!selectedFilename) &&
    (!runtimeRequiresVsCodeAgent(agentRuntime) || !!resolvedFilename);

  const dirty = note.trim().length > 0 || (mode === "custom" && !!selectedFilename);

  return (
    <Dialog
      open
      onClose={onClose}
      closeGuard={{ dirty, busy: isLaunching }}
      ariaLabel={mode === "suggested" ? "Run Sugerido" : "Run Personalizado"}
      size="md"
    >
        <div className={styles.modalHeader}>
          <span className={styles.modalIcon}>{mode === "suggested" ? "🤖" : "⚙️"}</span>
          <div className={styles.modalTitleBlock}>
            <div className={styles.modalTitle}>
              {mode === "suggested" ? "Run Sugerido" : "Run Personalizado"}
            </div>
            <div className={styles.modalSub}>
              {refDeTicket(tt, ticket.ado_id)} · {ticket.title.length > 48 ? ticket.title.slice(0, 48) + "…" : ticket.title}
            </div>
          </div>
          <button className={styles.modalClose} onClick={onClose}>✕</button>
        </div>

        {mode === "suggested" && suggestedLabel && (
          <div className={styles.modalAgentRow}>
            <span className={styles.modalAgentIcon}>▶</span>
            <span className={styles.modalAgentName}>{suggestedLabel}</span>
            {suggestedFilename ? (
              <span className={styles.modalAgentHint}>
                {suggestedFilename.replace(/\.agent\.md$/i, "")}
              </span>
            ) : (
              <span className={styles.modalAgentHint}>sin agente asignado en equipo</span>
            )}
          </div>
        )}

        {mode === "custom" && (
          <div className={styles.modalSection}>
            <label className={styles.modalLabel}>Agente</label>
            {vsCodeAgents.length === 0 ? (
              <p className={styles.modalEmpty}>No hay agentes configurados en VS Code.</p>
            ) : (
              <select
                className={styles.modalSelect}
                value={selectedFilename}
                onChange={(e) => setSelectedFilename(e.target.value)}
              >
                {vsCodeAgents.map((a) => (
                  <option key={a.filename} value={a.filename}>{a.name}</option>
                ))}
              </select>
            )}
          </div>
        )}

        <div className={styles.modalSection}>
          <AgentRuntimeSelector
            value={agentRuntime}
            onChange={setAgentRuntime}
            disabled={isLaunching}
          />
          <p className={styles.runtimeBadge}>
            Lanzará con: <strong>{runtimeDisplayLabel(agentRuntime)}</strong>
          </p>
          {/* Plan 212 F4 — TODOS los efforts, los no soportados anotados con a
              qué degradan. Nada se esconde ni se deshabilita. */}
          {pickerEnabled && (
            <ModelEffortPicker
              variant="block"
              catalog={modelCatalog.catalog?.[agentRuntime]}
              model={pickerModel}
              effort={pickerEffort}
              disabled={isLaunching}
              onChange={(n) => {
                setPickerModel(n.model);
                setPickerEffort(n.effort);
              }}
            />
          )}
          {/* Plan 288 F9 — de dónde salió esta lista y qué se descartó. */}
          <AvisoCatalogoModelos runtime={agentRuntime} />
          {runtimeRequiresVsCodeAgent(agentRuntime) && !resolvedFilename && (
            <p className={styles.modalEmpty}>
              Este runtime necesita un agente VS Code asignado para el ticket seleccionado.
            </p>
          )}
        </div>

        <div className={styles.modalSection}>
          <label className={styles.modalLabel}>
            Nota para el agente <span className={styles.modalOptional}>(opcional)</span>
          </label>
          <textarea
            className={styles.modalTextarea}
            placeholder="Instrucciones adicionales, contexto o aclaraciones para incluir en el chat de VS Code…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            autoFocus
          />
        </div>

        {errorMessage && (
          <div className={styles.modalError} role="alert">
            {errorMessage}
          </div>
        )}

        <div className={styles.modalActions}>
          <button className={styles.modalCancel} onClick={onClose} disabled={isLaunching}>
            Cancelar
          </button>
          <button
            className={styles.modalConfirm}
            onClick={() =>
              onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : suggestedFilename, {
                model: pickerModel,
                effort: pickerEffort,
              })
            }
            disabled={isLaunching || !canConfirm}
          >
            {isLaunching ? launchInProgressLabel(agentRuntime) : "▶ Ejecutar"}
          </button>
        </div>
    </Dialog>
  );
}

// ─── TicketCard ───────────────────────────────────────────────────────────────

interface TicketCardProps {
  ticket: Ticket;
  runningExecution: AgentExecution | null;
  vsCodeAgents: VsCodeAgent[];
  memoryBadge?: StackyMemoryTicketBadge | null;
  /** Feature #4 — mapa determinístico ado_state → agent_type cargado una vez en TicketBoard raíz */
  flowConfigMap: Map<string, string>;
  indent?: boolean;
  /** Plan 166 F5 — dev_resolver_enabled del mismo Incidents.status() que ya
   * consume el board (:715). */
  devResolverEnabled?: boolean;
  /** Plan 177 — dev_pr_enabled del mismo Incidents.status(); muestra el checkbox "Abrir PR". */
  devPrEnabled?: boolean;
  /** Plan 287 F7 — abre la ficha a pantalla completa. El gesto que el operador ya
   *  conoce (click = desplegar la tarjeta) NO cambia: esto SUMA un botón. */
  onAbrirFicha?: (id: number) => void;
}

function TicketCard({ ticket, runningExecution, vsCodeAgents, memoryBadge, flowConfigMap, indent, devResolverEnabled, devPrEnabled, onAbrirFicha }: TicketCardProps) {
  const qc = useQueryClient();
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const [expanded, setExpanded] = useState(false);
  const [runModal, setRunModal] = useState<"suggested" | "custom" | null>(null);
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  // B6: cancelación del run en curso desde el board.
  const [isCancelling, setIsCancelling] = useState(false);
  const [actionToast, setActionToast] = useState<ToastState | null>(null);
  const askConfirm = useConfirm();

  // Regla de negocio #7/#8 (preservada dentro de resolveSuggestedAgent): Tasks y
  // Épicas nunca proponen Negocio — ya tienen análisis previo / botón Funcional.
  const isEpic  = (ticket.work_item_type ?? "").toLowerCase() === "epic";
  // Distintivo visual de INCIDENCIA (Issue/Bug): badge de tipo rojo con ícono
  // + barra roja al costado de la tarjeta. Mismo criterio que habilita el Dev
  // Resolutor (isIncidentWorkItemType), así lo marcado y lo accionable coinciden.
  const isIncident = isIncidentWorkItemType(ticket.work_item_type);

  // B5 — recomendación con fallback (FlowConfig → pipeline_summary → por tipo).
  // Antes salía sólo de FlowConfig por estado: un Feature/Technical/Task en un
  // estado no mapeado quedaba sin sugerencia (botón deshabilitado). El resolver
  // compartido (mismo en árbol y grafo) agrega los fallbacks y preserva la
  // supresión de "business" en Tasks/Épicas cayendo al siguiente candidato.
  const nextSuggested = resolveSuggestedAgent({
    workItemType: ticket.work_item_type,
    adoState: ticket.ado_state,
    flowConfigMap,
    pipelineNext: ticket.pipeline_summary?.next_suggested ?? null,
  });
  const pipelineQ = useQuery({
    queryKey: ["ticket-pipeline", ticket.id],
    queryFn: () => Tickets.pipeline(ticket.id),
    enabled: expanded,
    staleTime: 30000,
  });

  const pipelineNext = pipelineQ.data?.next?.agent_type ?? null;
  const effectiveNext = pipelineNext || nextSuggested;
  const nextLabel = effectiveNext ? (NEXT_AGENT_LABELS[effectiveNext] ?? effectiveNext) : null;

  // Resuelve el filename del agente del equipo que corresponde al tipo sugerido.
  // Prioriza agentes pinneados ("Tu Equipo") sobre cualquier agente disponible.
  const suggestedFilename = effectiveNext
    ? findAgentFilenameByType(effectiveNext, vsCodeAgents, pinnedAgents)
    : null;

  // Plan 282 F4/F6 — el tracker del ticket, con FALLBACK al del proyecto:
  // el campo tracker_type del ticket es OPCIONAL en el payload legacy y sin fallback un proyecto
  // ADO pasaria a rotular "Tracker-1234" en todas sus tarjetas.
  const tt = trackerEfectivo(ticket.tracker_type, useWorkbench((s) => s.activeProject?.tracker_type ?? null));
  const isClosed = esEstadoCerrado(ticket.ado_state, tt);
  // Fuente dual: AgentExecution activa (prop) O stacky_status del ticket (BD)
  const isRunning = !isClosed && (!!runningExecution || ticket.stacky_status === "running");
  const runningAgentType = runningExecution?.agent_type ?? null;

  // Detección de estado INCONSISTENTE: stacky_status=completed + ejecución huérfana activa
  const inconsistency = detectInconsistencyFromRunning(ticket.stacky_status, runningExecution ?? null);

  const handleRunConfirm = useCallback(async (
    note: string,
    filename: string | null,
    overrides?: { model: string | null; effort: string | null },
  ) => {
    setIsLaunching(true);
    setLaunchError(null);
    try {
      const contextBlocks = note
        ? [{ id: "operator-note", kind: "editable" as const, title: "Nota del operador", content: note }]
        : [];
      const result = await launchAgentWithRuntime({
        ticketId: ticket.id,
        projectName: activeProjectName,
        runtime: agentRuntime,
        contextBlocks,
        vscodeAgent: findVsCodeAgent(vsCodeAgents, filename),
        // Plan 212 F4 — lo que el operador eligió en el modal manda; sin
        // elección explícita el backend usa su default de siempre.
        modelOverride: overrides?.model ?? null,
        effort: overrides?.effort ?? null,
      });
      // Runtimes CLI (Codex / Claude): abrir la consola in-page con el
      // execution_id para ver el streaming en vivo y poder responderle al agente.
      openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["executions"] }),
      ]);
      setRunModal(null);
    } catch (error) {
      setLaunchError(humanizeAgentLaunchError(error));
    } finally {
      setIsLaunching(false);
    }
  }, [activeProjectName, agentRuntime, pinnedAgents, qc, setCodexConsoleExecution, ticket.id, vsCodeAgents]);

  // B6: cancela el run activo del ticket. Requiere conocer la execution_id
  // (runningExecution); si el "running" viene sólo de stacky_status (huérfano)
  // no hay nada concreto que cancelar y el botón no se muestra.
  const handleCancelRun = useCallback(async () => {
    if (!runningExecution) return;
    if (!(await askConfirm({ title: "Cancelar run", message: "¿Cancelar el run en curso?", tone: "danger", confirmLabel: "Cancelar run", cancelLabel: "Volver" }))) return;
    setIsCancelling(true);
    try {
      await Executions.cancel(runningExecution.id);
    } catch (error) {
      // 409 = carrera: el run ya terminó entre el render y el click. No es un
      // error real para el operador; refrescamos y seguimos.
      const msg = error instanceof Error ? error.message : String(error);
      if (!msg.startsWith("409")) {
        setActionToast({ variant: "error", body: `No se pudo cancelar el run: ${msg}` });
      }
    } finally {
      setIsCancelling(false);
      // Claves que usa useRunningStatus + las listas de tickets para sacar el
      // ticket de "running" sin esperar al polling de 5s.
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["executions-active", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["executions-queued", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
      ]);
    }
  }, [activeProjectName, qc, runningExecution, askConfirm]);

  // Plan 166 F5 — "Resolver con agente": lanza el Dev Resolutor sobre esta
  // Issue. Modelo puro de disponibilidad en incidents/devResolverModel.ts
  // (RTL/jsdom no soporta tests de render de este componente — gap conocido).
  const [isResolvingIncident, setIsResolvingIncident] = useState(false);
  const canResolveIncident = canResolveWithAgent({
    workItemType: ticket.work_item_type,
    adoState: ticket.ado_state,
    isRunning,
    enabled: Boolean(devResolverEnabled),
    closedStates: sugerenciasDeEstadoCerrado(tt),
  });
  // Plan 177 — checkbox "Abrir PR" (premarcado).
  const [openPr, setOpenPr] = useState(DEFAULT_OPEN_PR);

  // 2026-08-02 — CHEQUEO PREVIO de repositorio git. Corre sólo cuando el ticket
  // admite el resolutor (no gasta un request por tarjeta del board). Sin esto el
  // operador tildaba "Abrir PR" a ciegas y, si el proyecto no tenía repo git, no
  // pasaba absolutamente nada ni había mensaje.
  const prPreflightQ = useQuery({
    queryKey: ["dev-pr-preflight", activeProjectName],
    queryFn: () => Incidents.devPrPreflight(activeProjectName),
    // Sólo con la tarjeta abierta (ahí viven los botones de lanzamiento). La
    // queryKey es por PROYECTO, así que N tarjetas abiertas siguen siendo 1 request.
    enabled: expanded && canResolveIncident && Boolean(devPrEnabled),
    staleTime: 60_000,
  });
  // Si el chequeo mismo se cae (backend abajo), NO se puede quedar en
  // "Verificando…" para siempre: se degrada a deshabilitado CON motivo.
  const preflight = prPreflightQ.data ?? (prPreflightQ.isError ? PREFLIGHT_CAIDO : null);
  const prControl = describeOpenPrControl({
    canResolve: canResolveIncident,
    devPrEnabled: Boolean(devPrEnabled),
    preflight,
    deseado: openPr,
  });

  // Resultado del auto-PR del ÚLTIMO run del resolutor sobre este ticket. Va por
  // TICKET y no por execution_id en memoria: así el resultado sigue ahí después
  // de recargar la página, que es cuando el operador vuelve a mirarlo.
  const prResultQ = useQuery({
    queryKey: ["dev-pr-result", ticket.id],
    queryFn: () => Incidents.devPrResultByTicket(ticket.id),
    enabled: expanded && canResolveIncident && Boolean(devPrEnabled),
    refetchInterval: (q) => (debeSeguirConsultando(q.state.data ?? null) ? 5_000 : false),
  });
  const [prLaunchAviso, setPrLaunchAviso] = useState<string | null>(null);
  const prResultado = describePrResult(prResultQ.data ?? null);

  const handleResolveWithAgent = useCallback(async () => {
    setIsResolvingIncident(true);
    setLaunchError(null);
    setPrLaunchAviso(null);
    try {
      // El resolutor no abre el modal de run, así que no hay elección por
      // corrida que propagar: el backend usa su default/selector adaptativo.
      // (El selector del plan 212 F4 vive en RunModal, donde sí se elige.)
      const result = await Incidents.runDevResolver({
        ticket_id: ticket.id,
        runtime: agentRuntime,
        project: activeProjectName,
        // Sólo se pide el PR si el chequeo previo dio verde Y el operador lo dejó
        // tildado: `prControl.checked` ya combina ambas cosas.
        open_pr: prControl.checked,
      });
      // El backend declara qué pasó con el pedido de PR: si lo rechazó, se dice
      // ACÁ y no se espera en vano un PR que nunca va a llegar.
      if (result.auto_pr?.requested && !result.auto_pr.accepted) {
        setPrLaunchAviso(result.auto_pr.message || "No se pudo pedir el PR automático.");
      }
      openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["executions"] }),
        // El run recién lanzado ya tiene su intent: que el bloque de resultado
        // lo tome sin esperar al próximo tick del polling.
        qc.invalidateQueries({ queryKey: ["dev-pr-result", ticket.id] }),
      ]);
    } catch (error) {
      setLaunchError(humanizeAgentLaunchError(error));
    } finally {
      setIsResolvingIncident(false);
    }
  }, [activeProjectName, agentRuntime, qc, setCodexConsoleExecution, ticket.id, prControl.checked]);

  return (
    <>
      <div className={`${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""} ${indent ? styles.cardIndented : ""} ${isIncident ? styles.cardIncident : ""}`}>

        {/* Banner: INCONSISTENTE (prioridad) o EN EJECUCIÓN */}
        {inconsistency.isInconsistent ? (
          <div className={styles.runningCardBanner} style={{ background: "rgba(245,158,11,0.18)", borderColor: "rgba(245,158,11,0.45)" }}>
            <span className="badge-inconsistente">INCONSISTENTE</span>
            <span style={{ fontSize: 11, color: "rgba(255,255,255,0.6)", marginLeft: 6 }}>
              ejecución #{inconsistency.orphanExecution.id} huérfana
            </span>
          </div>
        ) : isRunning && (
          <div className={styles.runningCardBanner}>
            <span className={styles.runningPulse} />
            <span>EN EJECUCIÓN</span>
            {runningAgentType && (
              <span className={styles.runningCardAgent}>{runningAgentType}</span>
            )}
          </div>
        )}

        {/* Header del ticket */}
        <div
          className={styles.cardHeader}
          data-card-header="true"
          onClick={() => setExpanded((x) => !x)}
        >
          <div className={styles.cardTop}>
            <span className={styles.adoId}>{refDeTicket(tt, ticket.ado_id)}</span>
            <span
              className={styles.stateBadge}
              style={{ background: `${stateColor(ticket.ado_state, tt)}22`, color: stateColor(ticket.ado_state, tt), border: `1px solid ${stateColor(ticket.ado_state, tt)}44` }}
            >
              {ticket.ado_state ?? "—"}
            </span>
            {ticket.work_item_type && !isEpic && (
              <span
                className={`${styles.wiTypeBadge} ${isIncident ? styles.wiTypeBadgeIncident : ""}`}
                title={isIncident ? "Incidencia" : ticket.work_item_type}
              >
                {formatWorkItemTypeLabel(ticket.work_item_type)}
              </span>
            )}
            {/* Plan 200 F4 — hay SQL para desplegar en este ticket. */}
            <TicketSqlDeployBadge ticketId={ticket.id} className={styles.priority} />
            {ticket.priority != null && (
              <span className={styles.priority}>P{ticket.priority}</span>
            )}
          </div>
          <p className={styles.cardTitle}>{ticket.title}</p>

          <div className={styles.cardActions} onClick={(e) => e.stopPropagation()}>
            {/* Plan 287 F7 — "Abrir ficha". Va acá, hermano del .map de quickActions
                e inmediatamente ANTES, porque este contenedor YA frena la
                propagación en su propia línea de apertura: el botón queda protegido
                del onClick que despliega la tarjeta sin sumar un freno nuevo (por eso
                el conteo de frenos del archivo tiene que quedar en 12, sin cambio; el
                nombre literal del método NO se escribe acá justamente porque el gate
                de F7 es un grep sobre el texto y un comentario lo inflaría igual).
                Y NO va DENTRO de quickActions: esa lista sale del catálogo de
                acciones con doble cerrojo y daría de alta una acción en el catálogo. */}
            {onAbrirFicha && (
              <IconButton
                size="sm"
                label="Abrir ficha"
                icon={<Maximize2 size={14} />}
                onClick={() => onAbrirFicha(ticket.id)}
              />
            )}
            {/* Plan 175 F4 — solo las acciones SEGURAS: quickActions filtra con
                doble cerrojo (quick Y safe), así que nada con efecto puede
                aparecer a un click de distancia en la tarjeta. */}
            {quickActions(actionsForTicket(ticket, tt)).map((a) => (
              <IconButton
                key={a.id}
                size="sm"
                label={a.label}
                icon={a.icon}
                onClick={() =>
                  void a.run({
                    copyText: copiarTexto,
                    openExternal: (url: string) => window.open(url, "_blank", "noopener"),
                    navigate: () => {},
                    askConfirm: async () => true,
                    api: {
                      cancelExecution: async () => ({}),
                      deleteExecution: async () => ({}),
                      publishExecution: async () => ({}),
                    },
                  })
                }
              />
            ))}
            {nextLabel && <span className={styles.nextTag}>→ {nextLabel}</span>}
            {memoryBadge && memoryBadge.open_findings > 0 && (
              <span
                className={`${styles.memoryFindingBadge} ${
                  memoryBadge.critical || memoryBadge.error ? styles.memoryFindingBadgeHot : ""
                }`}
                title={`Memoria: ${memoryBadge.open_findings} hallazgo(s) abierto(s)`}
              >
                Memoria {memoryBadge.open_findings}
              </span>
            )}
          </div>
        </div>

        {/* Detalle expandido */}
        {expanded && (
          <div className={styles.cardBody}>
            {/* Botón de recuperación de inconsistencia (visible siempre que aplique) */}
            {inconsistency.isInconsistent && ticket.ado_id && (
              <div style={{ marginBottom: 8 }} onClick={(e) => e.stopPropagation()}>
                <RecoverExecutionButton
                  adoId={ticket.ado_id}
                  ticketId={ticket.id}
                  orphanExecution={inconsistency.orphanExecution}
                />
              </div>
            )}

            {/* Botón de cierre manual: visible cuando el ticket aparece "en ejecución"
                (mismo criterio dual que el banner) y no hay inconsistencia activa.
                Usa isRunning para cubrir el caso donde runningExecution existe pero
                stacky_status quedó desincronizado (chat externo, race, reset). */}
            {isRunning && !inconsistency.isInconsistent && (
              <div style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
                <FinishWorkButton
                  ticket={ticket}
                  onCompleted={() => {
                    qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
                    qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
                  }}
                />
                {/* B6: cancelar el run sólo cuando hay una execution_id concreta. */}
                {runningExecution && (
                  <button
                    className={styles.cancelRunBtn}
                    onClick={handleCancelRun}
                    disabled={isCancelling}
                    title="Cancelar el run en curso (en GitHub Copilot la cancelación es cooperativa y puede tardar unos segundos)"
                  >
                    {isCancelling ? "⏳ Cancelando…" : "✕ Cancelar run"}
                  </button>
                )}
              </div>
            )}

            {/* Botón para crear Tasks hijas en ADO desde pending-task.json (Fase 2).
                Solo visible en Epics. El componente se auto-oculta si no hay pendientes. */}
            {isEpic && (
              <div style={{ marginBottom: 8 }} onClick={(e) => e.stopPropagation()}>
                <CreateChildTaskButton
                  epicAdoId={ticket.ado_id}
                  disabled={isRunning}
                  onTaskCreated={() => {
                    qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
                    qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
                  }}
                />
              </div>
            )}

            {/* Botones de ejecución */}
            <div className={styles.runButtons}>
              <button
                className={styles.runSuggestedBtn}
                onClick={(e) => { e.stopPropagation(); setLaunchError(null); setRunModal("suggested"); }}
                disabled={!nextSuggested || isRunning}
                title={
                  isRunning
                    ? "Hay un agente corriendo sobre este ticket — esperá a que termine"
                    : nextSuggested
                    ? `Correr agente sugerido: ${nextLabel}`
                    : ticket.ado_state
                    ? `No hay agente configurado para el estado '${ticket.ado_state}'. Configurá el flujo en la pestaña Estados.`
                    : `El ticket no tiene estado ${nombreDeTracker(tt)} asignado.`
                }
              >
                ▶ Run Sugerido
                {nextLabel && <span className={styles.runBtnHint}>{nextLabel}</span>}
              </button>
              <button
                className={styles.runCustomBtn}
                onClick={(e) => { e.stopPropagation(); setLaunchError(null); setRunModal("custom"); }}
                disabled={isRunning}
                title={isRunning ? "Hay un agente corriendo sobre este ticket" : undefined}
              >
                ⚙ Run Custom
              </button>
              {/* Plan 166 F5 — Dev Resolutor de Incidencias, solo en Issues/Bugs. */}
              {canResolveIncident && (
                <button
                  className={styles.resolveBtn}
                  onClick={(e) => { e.stopPropagation(); void handleResolveWithAgent(); }}
                  disabled={isResolvingIncident}
                  title="Resolver esta incidencia con un agente dev"
                >
                  {isResolvingIncident ? "⏳ Lanzando…" : "🔧 Resolver con agente"}
                </button>
              )}
              {/* Plan 177 + 2026-08-02 — tilde "Abrir PR". Cuando el PR no puede
                  salir el control NO desaparece: queda deshabilitado con el
                  motivo a la vista (degradación visible). */}
              {prControl.visible && (
                <label
                  className={styles.openPrCheckbox}
                  onClick={(e) => e.stopPropagation()}
                  title={prControl.motivo || "Al terminar, abrir un Pull Request con el fix y los tests"}
                >
                  <input
                    type="checkbox"
                    checked={prControl.checked}
                    onChange={(e) => setOpenPr(e.target.checked)}
                    disabled={isResolvingIncident || prControl.disabled}
                  />
                  {prControl.etiqueta}
                </label>
              )}
            </div>

            {/* Motivo por el que el tilde está deshabilitado / aviso del chequeo
                previo de repo git. Sin esto la casilla gris no explica nada. */}
            {prControl.visible && prControl.motivo && (
              <div className={styles.openPrMotivo} onClick={(e) => e.stopPropagation()}>
                {prControl.disabled ? "⚠ " : "ℹ "}
                {prControl.motivo}
              </div>
            )}

            {/* Aviso inmediato del lanzamiento: el backend rechazó el pedido de PR. */}
            {prLaunchAviso && (
              <div className={styles.openPrMotivo} onClick={(e) => e.stopPropagation()}>
                ⚠ {prLaunchAviso}
              </div>
            )}

            {/* RESULTADO del auto-PR: creado (con link), no creado (con motivo)
                o fallado (con el error). Antes esto sólo existía como comentario
                en la Issue del tracker; desde Stacky era invisible. */}
            {prResultado.visible && (
              <div
                className={`${styles.openPrResultado} ${styles[`openPrTono_${prResultado.tono}`] ?? ""}`}
                onClick={(e) => e.stopPropagation()}
              >
                <span>{prResultado.texto}</span>
                {prResultado.url && (
                  <a href={prResultado.url} target="_blank" rel="noreferrer noopener">
                    Ver el PR
                  </a>
                )}
              </div>
            )}

            {pipelineQ.data && (
              <div className={styles.ticketPipelineBox}>
                <div className={styles.ticketPipelineHeader}>
                  <span>Pipeline del ticket</span>
                  {pipelineQ.data.next && (
                    <span className={styles.ticketPipelineNext}>
                      siguiente: {pipelineQ.data.next.agent_type} ({pipelineQ.data.next.source})
                    </span>
                  )}
                </div>
                <div className={styles.ticketPipelineStages}>
                  {pipelineQ.data.stages.map((stage) => (
                    <span
                      key={stage.stage}
                      className={`${styles.ticketPipelineStage} ${stage.done ? styles.ticketPipelineStageDone : ""}`}
                      title={stage.evidence || stage.stage}
                    >
                      {stage.stage}
                      {stage.done ? " ✓" : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Análisis de estado con IA local: resumen + puntos débiles +
                incoherencias entre agentes, con TODO el contexto del ticket
                (épica, hijas, comentarios y outputs). Gratis, corre local. */}
            <TicketLocalInsightButton ticketId={ticket.id} />

            {ticket.description && (
              <details className={styles.descDetails}>
                <summary>Descripción</summary>
                <p className={styles.descText}>{ticket.description}</p>
              </details>
            )}

            {ticket.ado_url && (
              <a
                className={styles.adoLink}
                href={ticket.ado_url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                {accionAbrirEn(tt)}
              </a>
            )}
          </div>
        )}
      </div>

      {runModal && (
        <RunModal
          ticket={ticket}
          mode={runModal}
          suggestedLabel={nextLabel}
          suggestedFilename={suggestedFilename}
          vsCodeAgents={vsCodeAgents}
          isLaunching={isLaunching}
          errorMessage={launchError}
          onConfirm={handleRunConfirm}
          onClose={() => setRunModal(null)}
        />
      )}
      {actionToast && <Toast toast={actionToast} onClose={() => setActionToast(null)} />}
    </>
  );
}

// ─── EpicGroup ────────────────────────────────────────────────────────────────

interface EpicGroupProps {
  epic: TicketNode;
  runningByTicket: Map<number, AgentExecution>;
  vsCodeAgents: VsCodeAgent[];
  memoryBadges: Record<string, StackyMemoryTicketBadge>;
  /** Feature #4 — propagado desde TicketBoard raíz */
  flowConfigMap: Map<string, string>;
  /** Plan 166 F5 — propagado desde TicketBoard raíz */
  devResolverEnabled?: boolean;
  /** Plan 177 — dev_pr_enabled del mismo Incidents.status(); muestra el checkbox "Abrir PR". */
  devPrEnabled?: boolean;
  /** Plan 287 F7 — se propaga hasta TicketCard para el boton "Abrir ficha". */
  onAbrirFicha?: (id: number) => void;
}

function EpicGroup({ epic, runningByTicket, vsCodeAgents, memoryBadges, flowConfigMap, devResolverEnabled, devPrEnabled, onAbrirFicha }: EpicGroupProps) {
  const qc = useQueryClient();
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const [collapsed, setCollapsed] = useState(false);
  // Plan 172 F5 — teclado en las tarjetas. El índice vive en CADA grupo de
  // épica, que es el contenedor natural: un roving global tendría que saltar
  // entre grupos colapsables y el operador perdería la referencia.
  const cardRoving = useRovingFocus({
    itemCount: epic.children.length,
    // Enter reusa el toggle que ya existe, sin prop-drilling ni tocar el estado
    // interno de TicketCard.
    onOpen: (i) => {
      const el = cardRoving.containerProps.ref.current?.querySelector(
        `[data-roving-item="${i}"] [data-card-header]`,
      ) as HTMLElement | null;
      el?.click();
    },
  });
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const ttEpic = trackerEfectivo(epic.tracker_type, useWorkbench((s) => s.activeProject?.tracker_type ?? null));
  const isClosed = esEstadoCerrado(epic.ado_state, ttEpic);
  const runningExec = runningByTicket.get(epic.id) ?? null;
  const isRunning = !isClosed && !!runningExec;
  const functionalFilename = findAgentFilenameByType("functional", vsCodeAgents, pinnedAgents);

  const handleRunFunctional = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!functionalFilename) return;
    setIsLaunching(true);
    setLaunchError(null);
    try {
      const result = await launchAgentWithRuntime({
        ticketId: epic.id,
        projectName: activeProjectName,
        runtime: agentRuntime,
        contextBlocks: [],
        vscodeAgent: findVsCodeAgent(vsCodeAgents, functionalFilename),
      });
      // Runtimes CLI: abrir la consola in-page para ver el streaming en vivo.
      openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["executions"] }),
      ]);
    } catch (error) {
      setLaunchError(humanizeAgentLaunchError(error));
    } finally {
      setIsLaunching(false);
    }
  }, [activeProjectName, agentRuntime, epic.id, functionalFilename, pinnedAgents, qc, setCodexConsoleExecution, vsCodeAgents]);

  return (
    <div className={styles.epicGroup}>
      {/* Epic header */}
      <div className={`${styles.epicHeader} ${isClosed ? styles.epicClosed : ""}`}>
        <button
          className={styles.epicCollapseBtn}
          onClick={() => setCollapsed((x) => !x)}
          title={collapsed ? "Expandir" : "Colapsar"}
        >
          {collapsed ? "▶" : "▼"}
        </button>
        <span
          className={styles.epicBadge}
          style={{ color: getWorkItemTypeColor(epic.work_item_type) }}
        >
          {(epic.work_item_type ?? "EPIC").toUpperCase()}
        </span>
        <span className={styles.epicAdoId}>{refDeTicket(ttEpic, epic.ado_id)}</span>
        <span
          className={styles.epicState}
          style={{ color: stateColor(epic.ado_state, ttEpic), borderColor: `${stateColor(epic.ado_state, ttEpic)}44` }}
        >
          {epic.ado_state ?? "—"}
        </span>
        <span className={styles.epicTitle}>{epic.title}</span>
        <span className={styles.epicChildCount}>{epic.children.length} item{epic.children.length !== 1 ? "s" : ""}</span>
        {runningExec && !isClosed && (
          <span className={styles.epicRunningChip}>
            <span className={styles.runningPulse} /> EN EJECUCIÓN
          </span>
        )}
        {epic.ado_url && (
          <a className={styles.epicAdoLink} href={epic.ado_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>↗</a>
        )}
        {!isClosed && (
          <button
            className={styles.epicRunBtn}
            onClick={handleRunFunctional}
            disabled={isLaunching || isRunning || !functionalFilename}
            title={
              isRunning
                ? "Hay un agente corriendo sobre esta épica"
                : !functionalFilename
                ? "No hay agente funcional configurado en el equipo"
                : `Correr agente Funcional: ${functionalFilename?.replace(/\.agent\.md$/i, "")}`
            }
          >
            {isLaunching ? "⏳" : "🔍 Funcional"}
          </button>
        )}
      </div>
      {launchError && (
        <div style={{ marginTop: 8, fontSize: 11, color: "#fca5a5" }}>
          {launchError}
        </div>
      )}

      {/* Children */}
      {!collapsed && (
        <div
          className={styles.epicChildren}
          onKeyDown={cardRoving.containerProps.onKeyDown}
          ref={cardRoving.containerProps.ref as unknown as React.RefObject<HTMLDivElement>}
        >
          {epic.children.length === 0 ? (
            <div className={styles.epicNoChildren}>Sin tareas asociadas</div>
          ) : (
            epic.children.map((child, idx) => (
              <div key={child.id} {...cardRoving.rowProps(idx)}>
              <TicketCard
                key={child.id}
                ticket={child}
                runningExecution={runningByTicket.get(child.id) ?? null}
                vsCodeAgents={vsCodeAgents}
                memoryBadge={memoryBadges[String(child.id)] ?? null}
                flowConfigMap={flowConfigMap}
                indent
                devResolverEnabled={devResolverEnabled} devPrEnabled={devPrEnabled}
                onAbrirFicha={onAbrirFicha}
              />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ─── TicketBoard (página principal) ──────────────────────────────────────────

export default function TicketBoard({ ticket = null }: { ticket?: number | null } = {}) {
  const qc = useQueryClient();
  // ── Plan 287 F7 — la ficha del ticket a pantalla completa ─────────────────
  // El default `null` mantiene la compatibilidad con cualquier otro montaje.
  const [fichaTicketId, setFichaTicketId] = useState<number | null>(ticket);
  // C4 — sincronización con `popstate`: `route` es ESTADO VIVO en App (no un ref
  // congelado), así que el botón Atrás del navegador cambia `route.ticket` y la
  // prop llega. Sin este efecto la ficha se quedaría mostrando el ticket previo.
  useEffect(() => { setFichaTicketId(ticket); }, [ticket]);
  // Síncrono y fail-open a ON: el enlace directo no puede morir esperando una sonda.
  const fullViewOn = readCachedBoolFlag("STACKY_TICKET_FULLVIEW_ENABLED");

  /** Navegar NO cierra la ficha; la URL sigue al foco sin ensuciar el historial. */
  const irAFicha = useCallback((id: number | null) => {
    setFichaTicketId(id);
    try {
      const actual = parseRoute(window.location.pathname, window.location.search);
      const destino = serializeRoute({ ...actual, ticket: id ?? undefined });
      // replaceState y NO pushState: no queremos una entrada de historial por
      // cada salto de jerarquía.
      window.history.replaceState({}, "", destino);
    } catch {
      /* la navegación de la ficha nunca puede tumbar el tablero */
    }
  }, []);
  // Persistencia local de UX (plan 2026-05-27): filtros/checkboxes/preferencias
  // de la vista se rehidratan desde localStorage sin reconfiguración manual.
  const [search, setSearch] = useLocalStorageState<string>("ticketBoard.search", "");
  const [onlyPending, setOnlyPending] = useLocalStorageState<boolean>("ticketBoard.onlyPending", false);
  const [viewMode, setViewMode] = useLocalStorageState<ViewMode>("ticketBoard.viewMode", "graph");
  // Plan 38 B2 — Modal épica desde brief
  const [epicBriefOpen, setEpicBriefOpen] = useState(false);
  // Plan 131 — Modal resolutor de incidencias (botón invisible con flag OFF)
  const [incidentModalOpen, setIncidentModalOpen] = useState(false);
  const [incidentsEnabled, setIncidentsEnabled] = useState(false);
  // Plan 166 F5 — mismo consumo de Incidents.status() de arriba, extendido
  // con dev_resolver_enabled para el botón "Resolver con agente" del board.
  const [devResolverEnabled, setDevResolverEnabled] = useState(false);
  // Plan 177 — mismo Incidents.status(), campo dev_pr_enabled para el checkbox "Abrir PR".
  const [devPrEnabled, setDevPrEnabled] = useState(false);
  useEffect(() => {
    void (async () => {
      try {
        const s = await Incidents.status();
        setIncidentsEnabled(s.enabled);
        setDevResolverEnabled(Boolean(s.dev_resolver_enabled));
        setDevPrEnabled(Boolean(s.dev_pr_enabled));
      } catch {
        setIncidentsEnabled(false);
        setDevResolverEnabled(false);
        setDevPrEnabled(false);
      }
    })();
  }, []);
  // Requerimiento B: "Mostrar todas las tareas" — arranca MARCADO por defecto
  // (decisión de negocio). Al desmarcar se filtra a "solo asignadas a mí".
  const [showAll, setShowAll] = useLocalStorageState<boolean>("ticketBoard.showAll", true);

  // #3: Filtro de estados por agente activo
  const vsCodeAgent = useWorkbench((s) => s.vsCodeAgent);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const activeProject = useWorkbench((s) => s.activeProject);
  const activeProjectName = activeProject?.name ?? null;
  // Plan 276 F7 — tracker del proyecto activo, para los rótulos de la pantalla.
  const trackerType = activeProject?.tracker_type ?? null;
  const { data: memoryBadges = {} } = useQuery<Record<string, StackyMemoryTicketBadge>>({
    queryKey: ["memory-ticket-badges", activeProjectName],
    queryFn: () => Memory.ticketBadges(activeProjectName),
    // Plan §11: los badges por ticket son Fase B-F (diferidos). Solo se piden
    // si el flag avanzado está activo; así el board no se acopla al backend de
    // validación cuando la feature está OFF por default.
    enabled: !!activeProjectName && MEMORY_ADVANCED_ENABLED,
    staleTime: 30_000,
  });
  const activeAllowedStates: string[] = vsCodeAgent
    ? (agentWorkflows[vsCodeAgent.filename]?.allowed_states ?? [])
    : [];

  // Hook centralizado de estado running (fuente dual: stacky_status + executions polling)
  const { runningByTicket, runningTicketIds, getRunningTickets } = useRunningStatus();

  // P7: hook de auto-refresh con Page Visibility API y backoff.
  // Plan 156 F4: el reloj "hace Xs"/stale vive ahora en SyncStatusBar (hoja);
  // el hook ya no expone secondsSinceSync/isStale.
  // Plan 295 F10 — el intervalo sale del backend (flag del operador), con el 45 000
  // historico como fallback. UNA sola fuente para los DOS consumidores: el hook de
  // aca abajo y la barra de estado (mas abajo, en el JSX). Si solo se alimentara el
  // hook, la barra derivaria "stale" contra 45 s mientras el sync corre cada 180 s,
  // y el operador veria la barra en rojo permanente.
  const { data: cfgSync } = useQuery({
    queryKey: ["tickets", "config", "frontend"],
    queryFn: () => Tickets.frontendConfig(),
    staleTime: Infinity,   // se lee UNA vez al montar; no es un dato que cambie solo
    retry: false,          // si falla, el fallback alcanza: no hay que insistir
  });
  const intervaloSync = intervaloDeSync(
    cfgSync?.ticket_sync_interval_ms,
    TICKET_SYNC_INTERVAL_MS,
  );

  const {
    lastSyncedAt,
    isSyncing: isSyncingV2,
    syncError: syncErrorV2,
    triggerSync,
  } = useTicketSync({ intervalMs: intervaloSync, syncOnMount: true });

  const { data: tickets, isLoading, isError: isTicketsError, error: ticketsError, refetch: refetchTickets } = useQuery<Ticket[]>({
    queryKey: ["tickets", activeProjectName],
    queryFn: () => Tickets.list(activeProjectName),
    refetchInterval: 45_000,
    staleTime: 22_500,
    refetchOnWindowFocus: true,
  });

  const { data: hierarchy, isLoading: isHierarchyLoading, isError: isHierarchyError, error: hierarchyError, refetch: refetchHierarchy } = useQuery<TicketHierarchy>({
    queryKey: ["tickets-hierarchy", activeProjectName],
    queryFn: () => Tickets.hierarchy(activeProjectName),
    refetchInterval: 45_000,
    staleTime: 22_500,
    enabled: viewMode === "tree" || viewMode === "graph",
  });

  // Plan 135: error de PRIMERA carga (sin datos previos). react-query v5
  // conserva `data` del último fetch exitoso ante errores de refetch, así que
  // si hay data seguimos mostrando el board (stale) y NO lo tapamos con error.
  const ticketsUnavailable = isTicketsError && tickets === undefined;
  const hierarchyUnavailable = isHierarchyError && hierarchy === undefined;

  // Requerimiento B: identidad ADO del operador. Solo se resuelve cuando el
  // operador desmarca "Mostrar todas" (modo "Mis tareas"), para no golpear ADO
  // de más. linked=false ⇒ no filtramos (mostramos todo) para evitar lista vacía.
  const { data: adoUser } = useQuery({
    queryKey: ["ado-user", activeProjectName],
    queryFn: () => Tickets.adoUser(activeProjectName),
    enabled: !showAll && !!activeProjectName,
    staleTime: 10 * 60 * 1000,
  });
  const myUniqueName = adoUser?.linked ? (adoUser.ado_unique_name ?? null) : null;

  // Jerarquía a renderizar: cuando "Mis tareas" está activo y conocemos la
  // identidad ADO, podamos los nodos no asignados al operador. Una épica se
  // conserva si está asignada a mí o si tiene alguna tarea asignada a mí.
  const displayHierarchy = useMemo<TicketHierarchy | null>(() => {
    if (!hierarchy) return null;
    if (showAll || !myUniqueName) return hierarchy;
    // B1: matcheo tolerante (espeja `ado_identity.user_matches` del backend).
    // El `===` crudo anterior fallaba cuando assigned_to_ado guardaba el
    // displayName en vez del email, o por diferencias de casing/dominio →
    // board vacío. Normalizamos (trim+lowercase) y caemos a la parte local
    // antes de `@` para tolerar email vs uniqueName sin dominio.
    const norm = (s?: string | null) => (s ?? "").trim().toLowerCase();
    const localPart = (s?: string | null) => norm(s).split("@", 1)[0];
    const mine = (t: { assigned_to_ado?: string | null }) => {
      const a = norm(t.assigned_to_ado);
      const me = norm(myUniqueName);
      if (!a || !me) return false;
      return a === me || localPart(t.assigned_to_ado) === localPart(myUniqueName);
    };
    const epics = hierarchy.epics
      .map((e) => ({ ...e, children: e.children.filter(mine) }))
      .filter((e) => mine(e) || e.children.length > 0);
    const orphans = hierarchy.orphans.filter((o) => mine(o));
    return { epics, orphans };
  }, [hierarchy, showAll, myUniqueName]);

  // VsCode agents para el dropdown de Run Custom
  const { data: vsCodeAgents } = useQuery<VsCodeAgent[]>({
    queryKey: ["vscode-agents"],
    queryFn: Agents.vsCodeAgents,
    staleTime: 5 * 60 * 1000,
  });

  // Feature #4 — FlowConfig: cargar reglas una vez y construir map ado_state→agent_type.
  // La lista completa de reglas es chica (4-10 en práctica), no se llama resolve por ticket.
  const { data: flowConfigData } = useQuery({
    queryKey: ["flow-config", activeProjectName],
    queryFn: () => FlowConfig.list(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });
  // Keys normalizadas a lowercase para que la resolución no dependa del casing
  // del estado ADO sincronizado (ej. "Technical review" vs "Technical Review").
  const flowConfigMap = useMemo<Map<string, string>>(() => {
    const map = new Map<string, string>();
    for (const rule of flowConfigData?.rules ?? []) {
      map.set(rule.ado_state.trim().toLowerCase(), rule.agent_type);
    }
    return map;
  }, [flowConfigData]);

  // Filtrado para vista jerárquica (filtra dentro de epics + orphans)
  function filterNode(node: TicketNode): boolean {
    if (search) {
      const q = search.toLowerCase();
      const selfMatch = node.title.toLowerCase().includes(q) || String(node.ado_id).includes(q);
      const childMatch = node.children.some((c) => filterNode(c));
      if (!selfMatch && !childMatch) return false;
    }
    if (onlyPending && esEstadoCerrado(node.ado_state, trackerEfectivo(node.tracker_type, trackerType))) return false;
    // #3: si el agente activo tiene allowed_states, filtrar por estado
    if (activeAllowedStates.length > 0 && !activeAllowedStates.includes(node.ado_state ?? "")) {
      // Pero si tiene hijos que sí aplican, mostrar el nodo padre igual
      const childMatch = node.children.some((c) => activeAllowedStates.includes(c.ado_state ?? ""));
      if (!childMatch) return false;
    }
    return true;
  }

  const filteredEpics = (displayHierarchy?.epics ?? []).filter(filterNode);
  const filteredOrphans = (displayHierarchy?.orphans ?? []).filter((n) => filterNode(n as TicketNode));
  const totalHierarchy = filteredEpics.length + filteredOrphans.length;

  // Tickets activos (no cerrados) con ejecución en curso
  const runningTickets = getRunningTickets(
    (tickets ?? []).filter((t) => !esEstadoCerrado(t.ado_state, trackerEfectivo(t.tracker_type, trackerType)))
  );

  return (
    <div className={styles.root}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>📋</span>
          <h1 className={styles.title}>{tituloDeTickets(trackerType)}</h1>
          {viewMode === "tree" && (
            <span className={styles.count}>{totalHierarchy} grupos</span>
          )}
          {viewMode === "graph" && displayHierarchy && (
            <span className={styles.count}>
              {displayHierarchy.epics.length} épicas · {displayHierarchy.epics.reduce((a, e) => a + e.children.length, 0) + displayHierarchy.orphans.length} tareas
            </span>
          )}
          {runningTicketIds.size > 0 && (
            <span className={styles.headerRunningCount} title={`${runningTicketIds.size} ticket(s) con agente en ejecución`}>
              <span className={styles.headerRunningDot} />
              {runningTicketIds.size} corriendo
            </span>
          )}
        </div>
        <div className={styles.headerActions}>
          {/* Plan 38 B2 — Épica desde brief */}
          <button
            className={styles.syncBtn}
            onClick={() => setEpicBriefOpen(true)}
            title="Crear una nueva épica desde un brief de negocio"
          >
            + Nueva Épica desde brief
          </button>
          {/* Plan 131 — Resolutor de incidencias (invisible con flag OFF) */}
          {incidentsEnabled && (
            <button
              className={styles.syncBtn}
              onClick={() => setIncidentModalOpen(true)}
              title="Reportar una incidencia con fotos, archivos y texto"
            >
              🚑 Resolver incidencia
            </button>
          )}
          <IncidentInboxEntryButton /> {/* Plan 238 — bandeja de incidencias */}
          {/* Toggle vista */}
          <div className={styles.viewToggle}>
            <button
              className={`${styles.viewToggleBtn} ${viewMode === "tree" ? styles.viewToggleActive : ""}`}
              onClick={() => setViewMode("tree")}
              title="Vista jerárquica Epic → Tasks"
            >
              🌳 Jerárquica
            </button>
            <button
              className={`${styles.viewToggleBtn} ${viewMode === "graph" ? styles.viewToggleActive : ""}`}
              onClick={() => setViewMode("graph")}
              title="Vista grafo Epic → Tasks con conexiones visuales"
            >
              🔗 Grafo
            </button>
          </div>
          <AgentRuntimeSelector value={agentRuntime} onChange={setAgentRuntime} />
          <label className={styles.filterToggle}>
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
            />
            Solo abiertos
          </label>
          <label
            className={styles.filterToggle}
            title={
              showAll
                ? `Mostrando todas las tareas del proyecto. Desmarcá para ver solo las asignadas a vos en ${nombreDeTracker(trackerType)}.`
                : myUniqueName
                ? `Mostrando solo tareas asignadas a ${adoUser?.ado_display_name || myUniqueName}.`
                : `No se pudo resolver tu identidad en ${nombreDeTracker(trackerType)}; se muestran todas las tareas. Verificá el PAT del proyecto.`
            }
          >
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
            />
            Mostrar todas las tareas
            {!showAll && adoUser && !adoUser.linked && (
              <span style={{ marginLeft: 6, color: "#fbbf24", fontSize: 11 }}>
                {`⚠ ${nombreDeTracker(trackerType)} no vinculado`}
              </span>
            )}
          </label>
          {/* Error visual de sync */}
          {syncErrorV2 && (
            <div style={{ color: "#fff", background: "#b91c1c", padding: "6px 12px", borderRadius: 6, marginBottom: 8, maxWidth: 340, fontSize: 15, fontWeight: 500 }}>
              <span style={{ marginRight: 8 }}>⚠️</span>
              {syncErrorV2}
            </div>
          )}
          <button
            className={styles.syncBtn}
            onClick={triggerSync}
            disabled={isSyncingV2}
            title={`Sincronizar tickets desde ${nombreDeTracker(trackerType)}`}
          >
            {isSyncingV2 ? "↻ Sincronizando…" : `⟳ ${accionSincronizar(trackerType)}`}
          </button>
        </div>
      </header>

      {/* Plan 148 F6 — estado de integraciones no configuradas (ADO/Jira/LLM local) */}
      <IntegrationHealthBanner />

      {/* Plan 38 B2 — Modal Épica desde Brief */}
      {epicBriefOpen && (
        <EpicFromBriefModal
          onClose={() => setEpicBriefOpen(false)}
        />
      )}

      {/* Plan 131 — Modal Resolutor de Incidencias */}
      {incidentModalOpen && (
        <IncidentResolverModal
          onClose={() => setIncidentModalOpen(false)}
        />
      )}

      {/* P7: barra de estado de sincronizacion */}
      <SyncStatusBar
        lastSyncedAt={lastSyncedAt}
        isSyncing={isSyncingV2}
        syncError={syncErrorV2}
        onSyncClick={triggerSync}
        intervalMs={intervaloSync}
      />

      {/* Banner global de tickets en ejecución */}
      {runningTickets.length > 0 && (
        <div className={styles.activeExecutionsBanner}>
          <span className={styles.activeExecPulse} />
          <span className={styles.activeExecTitle}>
            {runningTickets.length === 1
              ? "1 ticket en ejecución"
              : `${runningTickets.length} tickets en ejecución`}
          </span>
          <div className={styles.activeExecChips}>
            {runningTickets.map((t) => {
              const exec = runningByTicket.get(t.id);
              return (
                <span key={t.id} className={styles.activeExecChip}>
                  {refDeTicket(trackerEfectivo(t.tracker_type, trackerType), t.ado_id)}
                  {exec && <span className={styles.activeExecChipAgent}>{exec.agent_type}</span>}
                  <span className={styles.activeExecChipTitle}>{t.title.slice(0, 28)}{t.title.length > 28 ? "…" : ""}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Banner de filtro por agente activo */}
      {activeAllowedStates.length > 0 && vsCodeAgent && (
        <div style={{ background: "#1e3a5f", color: "#7dd3fc", padding: "6px 16px", fontSize: 13, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #2563eb44" }}>
          <span>🤖 {vsCodeAgent.name}</span>
          <span style={{ color: "#94a3b8" }}>mostrando solo estados:</span>
          {activeAllowedStates.map((s) => (
            <span key={s} style={{ background: "#2563eb33", border: "1px solid #3b82f6", borderRadius: 4, padding: "1px 8px" }}>{s}</span>
          ))}
        </div>
      )}

      {/* Barra de búsqueda */}
      <div className={styles.searchBar}>
        <input
          className={styles.searchInput}
          placeholder={`Buscar por título o ${refDeTicket(trackerType, "ID")}…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {/* Plan 173 F3 — presets del tablero. Sus 4 campos ya persisten solos
            (useLocalStorageState), así que acá NO va `defaultFilters`: 173 no
            auto-aplica nada y se limita a guardar, aplicar y resaltar. */}
        <SavedViewsBar
          screenId="ticketBoard"
          currentFilters={ticketBoardStateToFilters({ search, onlyPending, showAll, viewMode })}
          onApply={(f) => {
            const st = filtersToTicketBoardState(f);
            setSearch(st.search);
            setOnlyPending(st.onlyPending);
            setShowAll(st.showAll);
            setViewMode(st.viewMode as ViewMode);
          }}
        />
      </div>

      {/* Lista */}
      <main className={styles.main}>
        {ticketsUnavailable && (
          <LoadErrorState
            what="los tickets"
            error={ticketsError}
            onRetry={() => { void refetchTickets(); }}
          />
        )}
        {/* Vista jerárquica */}
        {viewMode === "tree" && (
          <>
            {isHierarchyLoading && <SkeletonList rows={6} rowHeight={44} ariaLabel="Cargando tickets" />}
            {!isHierarchyLoading && hierarchyUnavailable && (
              <LoadErrorState
                what="la jerarquía de tickets"
                error={hierarchyError}
                onRetry={() => { void refetchHierarchy(); }}
              />
            )}
            {/* Guard C1 (§10.7): !hierarchyUnavailable ya excluye el caso de error (dominio 135) */}
            {!isHierarchyLoading && !hierarchyUnavailable && filteredEpics.length === 0 && filteredOrphans.length === 0 && (
              <EmptyState
                variant="tickets"
                message={`No hay tickets para este proyecto. Sincronizá con ${nombreDeTracker(trackerType)} para traerlos.`}
                actionLabel={accionSincronizar(trackerType)}
                onAction={triggerSync}
              />
            )}
            <div className={styles.treeView}>
              {filteredEpics.map((epic) => (
                <EpicGroup
                  key={epic.id}
                  epic={epic}
                  runningByTicket={runningByTicket}
                  vsCodeAgents={vsCodeAgents ?? []}
                  memoryBadges={memoryBadges}
                  flowConfigMap={flowConfigMap}
                  devResolverEnabled={devResolverEnabled} devPrEnabled={devPrEnabled}
                  onAbrirFicha={irAFicha}
                />
              ))}
              {filteredOrphans.length > 0 && (
                <div className={styles.orphanSection}>
                  <div className={styles.orphanHeader}>
                    <span className={styles.orphanBadge}>SIN EPIC</span>
                    <span className={styles.orphanCount}>{filteredOrphans.length} item{filteredOrphans.length !== 1 ? "s" : ""}</span>
                  </div>
                  <div className={styles.orphanGrid}>
                    {filteredOrphans.map((t) => (
                      <TicketCard
                        key={t.id}
                        ticket={t as Ticket}
                        runningExecution={runningByTicket.get(t.id) ?? null}
                        vsCodeAgents={vsCodeAgents ?? []}
                        memoryBadge={memoryBadges[String(t.id)] ?? null}
                        flowConfigMap={flowConfigMap}
                        devResolverEnabled={devResolverEnabled} devPrEnabled={devPrEnabled}
                        onAbrirFicha={irAFicha}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* Vista grafo */}
        {viewMode === "graph" && (
          <>
            {isHierarchyLoading && <div className={styles.loading}>Cargando grafo…</div>}
            {!isHierarchyLoading && (
              <TicketGraphView
                hierarchy={displayHierarchy}
                onSync={triggerSync}
                isSyncing={isSyncingV2}
                syncError={syncErrorV2}
                vsCodeAgents={vsCodeAgents ?? []}
                runningByTicket={runningByTicket}
                memoryBadges={memoryBadges}
                onAbrirFicha={irAFicha}
              />
            )}
          </>
        )}
      </main>

      {/* ── Plan 287 F7 — la ficha, montada UNA sola vez para toda la pantalla ──
          v2/C6 — `jerarquia={hierarchy}`, el árbol CRUDO. NUNCA `displayHierarchy`,
          que está filtrado por "mías": con el filtro puesto, un hijo o un hermano
          de otra persona no estaría en el árbol y la navegación moriría muda. */}
      {fullViewOn && fichaTicketId != null && (
        <TicketFullView
          ticketId={fichaTicketId}
          jerarquia={hierarchy}
          onCerrar={() => irAFicha(null)}
          onCambiarFoco={(id) => irAFicha(id)}
        />
      )}
    </div>
  );
}

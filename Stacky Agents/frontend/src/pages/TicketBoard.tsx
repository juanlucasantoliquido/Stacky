import React, { useState, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, FlowConfig, Executions, Memory, type StackyMemoryTicketBadge } from "../api/endpoints";
import { MEMORY_ADVANCED_ENABLED } from "../config/featureFlags";
import type { Ticket, TicketNode, TicketHierarchy, AgentExecution, VsCodeAgent } from "../types";
import AgentRuntimeSelector from "../components/AgentRuntimeSelector";
import { useTicketSync } from "../hooks/useTicketSync";
import { SyncStatusBar } from "../components/SyncStatusBar";
import TicketGraphView from "../components/TicketGraphView";
import RecoverExecutionButton from "../components/RecoverExecutionButton";
import FinishWorkButton from "../components/FinishWorkButton";
import CreateChildTaskButton from "../components/CreateChildTaskButton";
import EpicFromBriefModal from "../components/EpicFromBriefModal";
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
import { detectInconsistencyFromRunning } from "../utils/inconsistencyDetector";
import { resolveSuggestedAgent } from "../utils/resolveSuggestedAgent";
import styles from "./TicketBoard.module.css";

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

const ADO_STATE_COLORS: Record<string, string> = {
  "Active":             "#3b82f6",
  "In Progress":        "#3b82f6",
  "En Progreso":        "#3b82f6",
  "Resolved":           "#a855f7",
  "Committed":          "#f59e0b",
  "New":                "#6b7280",
  "Done":               "#22c55e",
  "Closed":             "#22c55e",
};

const CLOSED_STATES = ["Done", "Closed", "Resolved", "Removed", "Completed"];

const NEXT_AGENT_LABELS: Record<string, string> = {
  business:   "💼 Negocio",
  functional: "🔍 Funcional",
  technical:  "🔬 Técnico",
  developer:  "🚀 Dev",
  qa:         "✅ QA",
};

function stateColor(state?: string): string {
  if (!state) return "#6b7280";
  return ADO_STATE_COLORS[state] ?? "#6b7280";
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
  onConfirm: (note: string, filename: string | null) => void;
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
  const [note, setNote] = useState("");
  const [selectedFilename, setSelectedFilename] = useState<string>(vsCodeAgents[0]?.filename ?? "");
  const resolvedFilename = mode === "custom" ? (selectedFilename || null) : suggestedFilename;

  const canConfirm =
    (mode === "suggested" ? !!suggestedLabel : !!selectedFilename) &&
    (!runtimeRequiresVsCodeAgent(agentRuntime) || !!resolvedFilename);

  const modalContent = (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <span className={styles.modalIcon}>{mode === "suggested" ? "🤖" : "⚙️"}</span>
          <div className={styles.modalTitleBlock}>
            <div className={styles.modalTitle}>
              {mode === "suggested" ? "Run Sugerido" : "Run Personalizado"}
            </div>
            <div className={styles.modalSub}>
              ADO-{ticket.ado_id} · {ticket.title.length > 48 ? ticket.title.slice(0, 48) + "…" : ticket.title}
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
            onClick={() => onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : suggestedFilename)}
            disabled={isLaunching || !canConfirm}
          >
            {isLaunching ? launchInProgressLabel(agentRuntime) : "▶ Ejecutar"}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
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
}

function TicketCard({ ticket, runningExecution, vsCodeAgents, memoryBadge, flowConfigMap, indent }: TicketCardProps) {
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

  // Regla de negocio #7/#8 (preservada dentro de resolveSuggestedAgent): Tasks y
  // Épicas nunca proponen Negocio — ya tienen análisis previo / botón Funcional.
  const isEpic  = (ticket.work_item_type ?? "").toLowerCase() === "epic";

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

  const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "");
  // Fuente dual: AgentExecution activa (prop) O stacky_status del ticket (BD)
  const isRunning = !isClosed && (!!runningExecution || ticket.stacky_status === "running");
  const runningAgentType = runningExecution?.agent_type ?? null;

  // Detección de estado INCONSISTENTE: stacky_status=completed + ejecución huérfana activa
  const inconsistency = detectInconsistencyFromRunning(ticket.stacky_status, runningExecution ?? null);

  const handleRunConfirm = useCallback(async (note: string, filename: string | null) => {
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
    if (!window.confirm("¿Cancelar el run en curso?")) return;
    setIsCancelling(true);
    try {
      await Executions.cancel(runningExecution.id);
    } catch (error) {
      // 409 = carrera: el run ya terminó entre el render y el click. No es un
      // error real para el operador; refrescamos y seguimos.
      const msg = error instanceof Error ? error.message : String(error);
      if (!msg.startsWith("409")) {
        // eslint-disable-next-line no-alert
        window.alert(`No se pudo cancelar el run: ${msg}`);
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
  }, [activeProjectName, qc, runningExecution]);

  return (
    <>
      <div className={`${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""} ${indent ? styles.cardIndented : ""}`}>

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
        <div className={styles.cardHeader} onClick={() => setExpanded((x) => !x)}>
          <div className={styles.cardTop}>
            <span className={styles.adoId}>ADO-{ticket.ado_id}</span>
            <span
              className={styles.stateBadge}
              style={{ background: `${stateColor(ticket.ado_state)}22`, color: stateColor(ticket.ado_state), border: `1px solid ${stateColor(ticket.ado_state)}44` }}
            >
              {ticket.ado_state ?? "—"}
            </span>
            {ticket.priority != null && (
              <span className={styles.priority}>P{ticket.priority}</span>
            )}
          </div>
          <p className={styles.cardTitle}>{ticket.title}</p>

          <div className={styles.cardActions} onClick={(e) => e.stopPropagation()}>
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
                    ? `No hay agente configurado para el estado '${ticket.ado_state}'. Configurá el flujo en la pestaña Config de Flujo.`
                    : "El ticket no tiene estado ADO asignado."
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
            </div>

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
                Abrir en Azure DevOps ↗
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
}

function EpicGroup({ epic, runningByTicket, vsCodeAgents, memoryBadges, flowConfigMap }: EpicGroupProps) {
  const qc = useQueryClient();
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const [collapsed, setCollapsed] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const isClosed = CLOSED_STATES.includes(epic.ado_state ?? "");
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
        <span className={styles.epicBadge}>EPIC</span>
        <span className={styles.epicAdoId}>ADO-{epic.ado_id}</span>
        <span
          className={styles.epicState}
          style={{ color: stateColor(epic.ado_state), borderColor: `${stateColor(epic.ado_state)}44` }}
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
        <div className={styles.epicChildren}>
          {epic.children.length === 0 ? (
            <div className={styles.epicNoChildren}>Sin tareas asociadas</div>
          ) : (
            epic.children.map((child) => (
              <TicketCard
                key={child.id}
                ticket={child}
                runningExecution={runningByTicket.get(child.id) ?? null}
                vsCodeAgents={vsCodeAgents}
                memoryBadge={memoryBadges[String(child.id)] ?? null}
                flowConfigMap={flowConfigMap}
                indent
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ─── TicketBoard (página principal) ──────────────────────────────────────────

export default function TicketBoard() {
  const qc = useQueryClient();
  // Persistencia local de UX (plan 2026-05-27): filtros/checkboxes/preferencias
  // de la vista se rehidratan desde localStorage sin reconfiguración manual.
  const [search, setSearch] = useLocalStorageState<string>("ticketBoard.search", "");
  const [onlyPending, setOnlyPending] = useLocalStorageState<boolean>("ticketBoard.onlyPending", false);
  const [viewMode, setViewMode] = useLocalStorageState<ViewMode>("ticketBoard.viewMode", "graph");
  // Plan 38 B2 — Modal épica desde brief
  const [epicBriefOpen, setEpicBriefOpen] = useState(false);
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

  // P7: hook de auto-refresh con Page Visibility API y backoff
  const {
    lastSyncedAt,
    secondsSinceSync,
    isSyncing: isSyncingV2,
    syncError: syncErrorV2,
    triggerSync,
    isStale,
  } = useTicketSync({ intervalMs: 45_000, syncOnMount: true });

  const { data: tickets, isLoading } = useQuery<Ticket[]>({
    queryKey: ["tickets", activeProjectName],
    queryFn: () => Tickets.list(activeProjectName),
    refetchInterval: 45_000,
    staleTime: 22_500,
    refetchOnWindowFocus: true,
  });

  const { data: hierarchy, isLoading: isHierarchyLoading } = useQuery<TicketHierarchy>({
    queryKey: ["tickets-hierarchy", activeProjectName],
    queryFn: () => Tickets.hierarchy(activeProjectName),
    refetchInterval: 45_000,
    staleTime: 22_500,
    enabled: viewMode === "tree" || viewMode === "graph",
  });

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
    if (onlyPending && CLOSED_STATES.includes(node.ado_state ?? "")) return false;
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
    (tickets ?? []).filter((t) => !CLOSED_STATES.includes(t.ado_state ?? ""))
  );

  return (
    <div className={styles.root}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>📋</span>
          <h1 className={styles.title}>Tickets ADO</h1>
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
                ? "Mostrando todas las tareas del proyecto. Desmarcá para ver solo las asignadas a vos en ADO."
                : myUniqueName
                ? `Mostrando solo tareas asignadas a ${adoUser?.ado_display_name || myUniqueName}.`
                : "No se pudo resolver tu identidad ADO; se muestran todas las tareas. Verificá el PAT del proyecto."
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
                ⚠ ADO no vinculado
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
            title="Sincronizar tickets desde ADO"
          >
            {isSyncingV2 ? "↻ Sincronizando…" : "⟳ Sincronizar ADO"}
          </button>
        </div>
      </header>

      {/* Plan 38 B2 — Modal Épica desde Brief */}
      {epicBriefOpen && (
        <EpicFromBriefModal
          onClose={() => setEpicBriefOpen(false)}
        />
      )}

      {/* P7: barra de estado de sincronizacion */}
      <SyncStatusBar
        lastSyncedAt={lastSyncedAt}
        secondsSinceSync={secondsSinceSync}
        isSyncing={isSyncingV2}
        syncError={syncErrorV2}
        onSyncClick={triggerSync}
        isStale={isStale}
        intervalMs={45_000}
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
                  ADO-{t.ado_id}
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
          placeholder="Buscar por título o ADO-ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Lista */}
      <main className={styles.main}>
        {/* Vista jerárquica */}
        {viewMode === "tree" && (
          <>
            {isHierarchyLoading && <div className={styles.loading}>Cargando jerarquía…</div>}
            {!isHierarchyLoading && filteredEpics.length === 0 && filteredOrphans.length === 0 && (
              <div className={styles.empty}>
                No hay tickets. Hacé clic en «Sincronizar ADO».
              </div>
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
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

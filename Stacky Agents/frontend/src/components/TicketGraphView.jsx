import React, { useState, useCallback, useRef, useLayoutEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FlowConfig } from "../api/endpoints";
import {
  findVsCodeAgent,
  humanizeAgentLaunchError,
  inferAgentTypeFromFilename,
  launchAgentWithRuntime,
  launchInProgressLabel,
  runtimeRequiresVsCodeAgent,
} from "../services/agentLaunch";
import { useWorkbench } from "../store/workbench";
import AgentRuntimeSelector from "./AgentRuntimeSelector";

// Feature #4 (mejora post-SDD): la inferencia LLM (Tickets.adoPipelineStatus)
// fue removida del consumo del frontend. Los chips muestran progreso a partir
// de pipeline_summary (datos BD locales). next_suggested para tickets normales
// se resuelve desde FlowConfig (mapping determinístico ado_state → agent_type).
import RecoverExecutionButton from "./RecoverExecutionButton";
import FinishWorkButton from "./FinishWorkButton";
import CreateChildTaskButton from "./CreateChildTaskButton";
import { detectInconsistencyFromRunning } from "../utils/inconsistencyDetector";
import styles from "./TicketGraphView.module.css";

// Misma lógica que TicketBoard — infiere tipo de agente desde filename.
function inferType(filename) {
  return inferAgentTypeFromFilename(filename);
}

function findAgentFilenameByType(agentType, vsCodeAgents, pinnedFilenames) {
  const pinnedMatch = pinnedFilenames.find((f) => inferType(f) === agentType);
  if (pinnedMatch) return pinnedMatch;
  const anyMatch = (vsCodeAgents || []).find((a) => inferType(a.filename) === agentType);
  return anyMatch ? anyMatch.filename : null;
}

// ─── Constantes de colores ────────────────────────────────────────────────────

const STATE_COLORS = {
  "Active":       { bg: "#1e3a5f", border: "#3b82f6", text: "#93c5fd" },
  "In Progress":  { bg: "#1e3a5f", border: "#3b82f6", text: "#93c5fd" },
  "En Progreso":  { bg: "#1e3a5f", border: "#3b82f6", text: "#93c5fd" },
  "Resolved":     { bg: "#2d1b69", border: "#a855f7", text: "#d8b4fe" },
  "Committed":    { bg: "#3d2a0a", border: "#f59e0b", text: "#fcd34d" },
  "New":          { bg: "#1a1a2e", border: "#6b7280", text: "#9ca3af" },
  "Done":         { bg: "#052e16", border: "#22c55e", text: "#86efac" },
  "Closed":       { bg: "#052e16", border: "#22c55e", text: "#86efac" },
  "Removed":      { bg: "#111", border: "#374151", text: "#4b5563" },
};

const EPIC_COLORS = { bg: "#1e1040", border: "#7c3aed", text: "#c4b5fd" };

const AGENT_LABELS = {
  business:   { icon: "💼", label: "Negocio" },
  functional: { icon: "🔍", label: "Funcional" },
  technical:  { icon: "🔬", label: "Técnico" },
  developer:  { icon: "🚀", label: "Dev" },
  qa:         { icon: "✅", label: "QA" },
};

// ─── Epic pipeline: 2 etapas locales ──────────────────────────────────────────

function epicPipelineSummary(epicNode) {
  const hasChildren = epicNode.children && epicNode.children.length > 0;
  return {
    done_stages: hasChildren ? ["created", "functional_breakdown"] : ["created"],
    next_suggested: hasChildren ? null : "functional",
    overall_progress: hasChildren ? 1.0 : 0.5,
  };
}

// ─── RunModal (grafo) ─────────────────────────────────────────────────────────

function RunModal({ ticket, mode, suggestedLabel, suggestedFilename, vsCodeAgents, isLaunching, errorMessage, onConfirm, onClose }) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const [note, setNote] = useState("");
  const [selectedFilename, setSelectedFilename] = useState(vsCodeAgents[0]?.filename ?? "");
  const resolvedFilename = mode === "custom" ? (selectedFilename || null) : suggestedFilename;
  const canConfirm =
    (mode === "suggested" ? !!suggestedLabel : !!selectedFilename) &&
    (!runtimeRequiresVsCodeAgent(agentRuntime) || !!resolvedFilename);

  const modalContent = (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <span className={styles.modalIcon}>{mode === "suggested" ? "🤖" : "⚙️"}</span>
          <div className={styles.modalTitleBlock}>
            <div className={styles.modalTitle}>{mode === "suggested" ? "Run Sugerido" : "Run Personalizado"}</div>
            <div className={styles.modalSub}>ADO-{ticket.ado_id} · {ticket.title.length > 48 ? ticket.title.slice(0, 48) + "…" : ticket.title}</div>
          </div>
          <button className={styles.modalClose} onClick={onClose}>✕</button>
        </div>

        {mode === "suggested" && suggestedLabel && (
          <div className={styles.modalAgentRow}>
            <span className={styles.modalAgentIcon}>▶</span>
            <span className={styles.modalAgentName}>{suggestedLabel}</span>
            {suggestedFilename ? (
              <span className={styles.modalAgentHint}>{suggestedFilename.replace(/\.agent\.md$/i, "")}</span>
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
                onChange={e => setSelectedFilename(e.target.value)}
              >
                {vsCodeAgents.map(a => <option key={a.filename} value={a.filename}>{a.name}</option>)}
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
          {runtimeRequiresVsCodeAgent(agentRuntime) && !resolvedFilename && (
            <p className={styles.modalEmpty}>
              Este runtime necesita un agente VS Code asignado para el ticket seleccionado.
            </p>
          )}
        </div>

        <div className={styles.modalSection}>
          <label className={styles.modalLabel}>Nota para el agente <span className={styles.modalOptional}>(opcional)</span></label>
          <textarea
            className={styles.modalTextarea}
            placeholder="Instrucciones adicionales para el agente…"
            value={note}
            onChange={e => setNote(e.target.value)}
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
          <button className={styles.modalCancel} onClick={onClose} disabled={isLaunching}>Cancelar</button>
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

// ─── PipelineBar ──────────────────────────────────────────────────────────────

function PipelineBar({ summary, isEpic, inferResult, compact = false, flowNext = null }) {
  if (isEpic) {
    const { done_stages, next_suggested } = summary;
    const stages = [
      { key: "created",              icon: "📌", label: "Creado" },
      { key: "functional_breakdown", icon: "🔍", label: "Desglose" },
    ];
    return (
      <div className={styles.pipelineBar}>
        {stages.map(s => (
          <span
            key={s.key}
            className={`${styles.stageChip} ${done_stages.includes(s.key) ? styles.chipDone : styles.chipPending} ${s.key === next_suggested ? styles.chipNext : ""}`}
          >
            {s.icon} {!compact && s.label}
            {done_stages.includes(s.key) && <span className={styles.tick}>✓</span>}
          </span>
        ))}
        {next_suggested && (
          <span className={styles.nextBadgeEpic}>→ Analista Funcional</span>
        )}
      </div>
    );
  }

  // Ticket normal
  const STAGES = ["business", "functional", "technical", "developer", "qa"];
  const done = inferResult
    ? Object.entries(inferResult.stages || {}).filter(([, v]) => v.done).map(([k]) => k)
    : (summary?.done_stages || []);
  // Sugerencia determinística desde FlowConfig (override). Si no se pasa,
  // cae a la lógica heredada (BD/LLM) — pero el caller principal siempre
  // pasa flowNext en este flujo.
  const next = flowNext ?? inferResult?.next_suggested ?? summary?.next_suggested ?? null;

  return (
    <div className={styles.pipelineBar}>
      {STAGES.map(s => {
        const ag = AGENT_LABELS[s];
        const isDone = done.includes(s);
        const isNext = s === next;
        return (
          <span
            key={s}
            className={`${styles.stageChip} ${isDone ? styles.chipDone : styles.chipPending} ${isNext ? styles.chipNext : ""}`}
            title={inferResult?.stages?.[s]?.evidence || ""}
          >
            {ag.icon}
            {!compact && <span className={styles.chipLabel}>{ag.label}</span>}
            {isDone && <span className={styles.tick}>✓</span>}
          </span>
        );
      })}
      {next && AGENT_LABELS[next] && (
        <span className={styles.nextBadge}>
          → {AGENT_LABELS[next].icon} <strong>{AGENT_LABELS[next].label}</strong>
        </span>
      )}
    </div>
  );
}

// ─── Error boundary por nodo ──────────────────────────────────────────────────
// Si un TicketNodeCard lanza durante el render (p.ej. inferMap o runningByTicket
// con shape inesperada), se aísla en su contenedor y muestra un fallback en
// lugar de blanquear toda la graph view.

export class NodeErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[TicketGraphView] node render error:", error, info);
  }
  render() {
    if (this.state.hasError) {
      const adoId = this.props.adoId ?? "?";
      const msg = this.state.error?.message || "error inesperado";
      return (
        <div
          role="alert"
          style={{
            padding: "8px 10px",
            background: "rgba(239,68,68,0.12)",
            border: "1px solid rgba(239,68,68,0.45)",
            borderRadius: 8,
            color: "#fecaca",
            fontSize: 12,
            lineHeight: 1.4,
            maxWidth: 240,
          }}
        >
          <strong>Error al renderizar ADO-{adoId}</strong>
          <div style={{ marginTop: 4, opacity: 0.85 }}>{msg}</div>
          <div style={{ marginTop: 4, opacity: 0.6 }}>Recargá la página para reintentar.</div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── TicketNode Card ──────────────────────────────────────────────────────────

function TicketNodeCard({ ticket, inferMap, onInfer, isEpic = false, vsCodeAgents = [], runningByTicket = new Map(), flowConfigMap = new Map() }) {
  const qc = useQueryClient();
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const pinnedAgents = useWorkbench((s) => s.pinnedAgents);
  const [expanded, setExpanded] = useState(false);
  const [runModal, setRunModal] = useState(null); // null | "suggested" | "custom"
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchError, setLaunchError] = useState(null);

  const inferResult = inferMap[ticket.id] || null;
  const colors = isEpic ? EPIC_COLORS : (STATE_COLORS[ticket.ado_state] || STATE_COLORS["New"]);
  const summary = isEpic ? epicPipelineSummary(ticket) : ticket.pipeline_summary;
  // Feature #4: sugerencia determinística desde FlowConfig en lugar de
  // summary.next_suggested (BD local que siempre devuelve la primera etapa
  // no completada → "business" para tickets sin progreso).
  const isTask = (ticket.work_item_type || "").toLowerCase() === "task";
  const flowAgentType = !isEpic && ticket.ado_state
    ? (flowConfigMap.get(ticket.ado_state.trim().toLowerCase()) ?? null)
    : null;
  // Regla #7/#8: Tasks y Épicas nunca proponen Negocio
  const flowNext = (isTask && flowAgentType === "business") ? null : flowAgentType;
  const next = isEpic ? summary.next_suggested : flowNext;
  const nextLabel = next && AGENT_LABELS[next] ? `${AGENT_LABELS[next].icon} ${AGENT_LABELS[next].label}` : null;
  const suggestedFilename = next ? findAgentFilenameByType(next, vsCodeAgents, pinnedAgents) : null;
  const runningExecution = runningByTicket.get(ticket.id) ?? null;
  const isRunning = !!runningExecution || runningByTicket.has(ticket.id);
  const isClosed = ["Done", "Closed", "Resolved", "Removed", "Completed"].includes(ticket.ado_state);

  // Detección de INCONSISTENTE: stacky_status=completed + ejecución huérfana activa
  const inconsistency = detectInconsistencyFromRunning(ticket.stacky_status, runningExecution);

  const handleLaunch = useCallback(async (note, filename) => {
    setIsLaunching(true);
    setLaunchError(null);
    try {
      const contextBlocks = note
        ? [{ id: "operator-note", kind: "editable", title: "Nota del operador", content: note }]
        : [];
      await launchAgentWithRuntime({
        ticketId: ticket.id,
        projectName: activeProjectName,
        runtime: agentRuntime,
        contextBlocks,
        vscodeAgent: findVsCodeAgent(vsCodeAgents, filename),
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["executions-active", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["executions-queued", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] }),
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] }),
      ]);
      setRunModal(null);
    } catch (error) {
      setLaunchError(humanizeAgentLaunchError(error));
    } finally {
      setIsLaunching(false);
    }
  }, [activeProjectName, agentRuntime, pinnedAgents, qc, ticket.id, vsCodeAgents]);

  return (
    <>
      <div
        className={`${styles.nodeCard} ${isEpic ? styles.epicCard : ""} ${expanded ? styles.nodeExpanded : ""} ${isRunning ? styles.nodeRunning : ""}`}
        style={{ background: colors.bg, borderColor: isRunning ? "#22c55e" : colors.border }}
        onClick={() => setExpanded(x => !x)}
      >
        {inconsistency.isInconsistent ? (
          <div className={styles.nodeRunningBanner} style={{ background: "rgba(245,158,11,0.18)", borderColor: "rgba(245,158,11,0.5)" }}>
            <span className="badge-inconsistente">INCONSISTENTE</span>
          </div>
        ) : isRunning && (
          <div className={styles.nodeRunningBanner}>
            <span className={styles.runningPulse} /> EN EJECUCIÓN
          </div>
        )}

        {/* Header */}
        <div className={styles.nodeHeader}>
          <div className={styles.nodeTopRow}>
            {isEpic && <span className={styles.epicBadge}>⚡ EPIC</span>}
            <span className={styles.nodeAdoId} style={{ color: colors.text }}>ADO-{ticket.ado_id}</span>
            <span className={styles.nodeStateBadge} style={{ color: colors.text, borderColor: colors.border }}>
              {ticket.ado_state || "—"}
            </span>
            {!isEpic && ticket.work_item_type && (
              <span className={styles.wiType}>{ticket.work_item_type}</span>
            )}
            {/* Botón Run compacto visible en todos los nodos (épicas y tickets) */}
            {!isClosed && (
              <button
                className={styles.runBtnCompact}
                title={nextLabel ? `Run sugerido: ${nextLabel}` : "Run personalizado"}
                onClick={e => { e.stopPropagation(); setLaunchError(null); setRunModal(next ? "suggested" : "custom"); }}
              >
                ▶
              </button>
            )}
          </div>
          <p className={styles.nodeTitle} style={{ color: "#e2e8f0" }}>{ticket.title}</p>

          {/* Pipeline compacta */}
          <PipelineBar
            summary={summary}
            isEpic={isEpic}
            inferResult={inferResult}
            compact
            flowNext={isEpic ? null : flowNext}
          />

          {/* Next agent prominente */}
          {next && !isEpic && (
            <div className={styles.nextAgentRow} onClick={e => e.stopPropagation()}>
              <span className={styles.nextAgentLabel}>
                Próximo: {AGENT_LABELS[next]?.icon} <strong style={{ color: "#fbbf24" }}>{AGENT_LABELS[next]?.label}</strong>
              </span>
            </div>
          )}
        </div>

        {/* Expandido */}
        {expanded && (
          <div className={styles.nodeBody} onClick={e => e.stopPropagation()}>

            {ticket.description && (
              <p className={styles.nodeDesc}>{ticket.description.slice(0, 300)}{ticket.description.length > 300 ? "…" : ""}</p>
            )}
            {ticket.ado_url && (
              <a className={styles.adoLink} href={ticket.ado_url} target="_blank" rel="noreferrer">
                Abrir en ADO ↗
              </a>
            )}

            {/* Botón de recuperación de inconsistencia */}
            {!isEpic && inconsistency.isInconsistent && ticket.ado_id && (
              <div style={{ marginBottom: 8 }} onClick={(e) => e.stopPropagation()}>
                <RecoverExecutionButton
                  adoId={ticket.ado_id}
                  ticketId={ticket.id}
                  orphanExecution={inconsistency.orphanExecution}
                  compact
                />
              </div>
            )}

            {/* Botón de cierre manual: solo en nodo expandido, ticket aparece como
                "en ejecución" (dual-source con isRunning) y sin inconsistencia activa
                ni ticket cerrado. Permite cerrar tickets que quedaron colgados aunque
                stacky_status no esté en "running" exacto. */}
            {!isEpic && !isClosed && isRunning && !inconsistency.isInconsistent && (
              <div style={{ marginBottom: 8 }} onClick={(e) => e.stopPropagation()}>
                <FinishWorkButton
                  ticket={ticket}
                  onCompleted={() => {
                    qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
                    qc.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
                  }}
                />
              </div>
            )}

            {/* Crear Tasks hijas en ADO desde pending-task.json (Fase 2).
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

            {/* Botones Run expandidos */}
            {!isClosed && (
              <div className={styles.runButtons}>
                <button
                  className={styles.runSuggestedBtn}
                  disabled={!next}
                  onClick={() => { setLaunchError(null); setRunModal("suggested"); }}
                  title={nextLabel ? `Correr: ${nextLabel}` : isEpic ? "Lanzar Analista Funcional" : "Esperando inferencia…"}
                >
                  {isEpic ? "🔍 Lanzar Funcional" : "▶ Run Sugerido"}
                  {nextLabel && <span className={styles.runBtnHint}>{nextLabel}</span>}
                </button>
                <button
                  className={styles.runCustomBtn}
                  onClick={() => { setLaunchError(null); setRunModal("custom"); }}
                >
                  ⚙ Run Custom
                </button>
              </div>
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
          onConfirm={handleLaunch}
          onClose={() => setRunModal(null)}
        />
      )}
    </>
  );
}

// ─── EpicGroup ────────────────────────────────────────────────────────────────

function computeLines(containerRef) {
  if (!containerRef.current) return [];
  const container = containerRef.current;
  const epicEl = container.querySelector("[data-role='epic-node']");
  const childEls = container.querySelectorAll("[data-role='child-node']");
  if (!epicEl || !childEls.length) return [];

  const cRect = container.getBoundingClientRect();
  const eRect = epicEl.getBoundingClientRect();
  const epicCenterX = eRect.left - cRect.left + eRect.width / 2;
  const epicBottom  = eRect.bottom - cRect.top;

  const newLines = [];
  childEls.forEach(el => {
    const r = el.getBoundingClientRect();
    const cx = r.left - cRect.left + r.width / 2;
    const cy = r.top - cRect.top;
    newLines.push({ x1: epicCenterX, y1: epicBottom, x2: cx, y2: cy });
  });
  return newLines;
}

function EpicGroup({ epic, inferMap, onInfer, vsCodeAgents, runningByTicket, flowConfigMap }) {
  const containerRef = useRef(null);
  const [lines, setLines] = useState([]);

  // useLayoutEffect: se ejecuta post-paint, coords reales del DOM
  useLayoutEffect(() => {
    if (!epic.children.length) { setLines([]); return; }
    setLines(computeLines(containerRef));

    // ResizeObserver: recalcular si el contenedor cambia de tamaño (wrap, zoom, etc.)
    const ro = new ResizeObserver(() => setLines(computeLines(containerRef)));
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [epic.children.length, epic.id]);

  return (
    <div className={styles.epicGroup} ref={containerRef}>
      {/* SVG lines */}
      <svg className={styles.connectorSvg} aria-hidden="true">
        {lines.map((l, i) => (
          <line
            key={i}
            x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
            stroke="rgba(124,58,237,0.4)"
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />
        ))}
      </svg>

      {/* Epic node */}
      <div data-role="epic-node" className={styles.epicNodeWrap}>
        <NodeErrorBoundary adoId={epic.ado_id}>
          <TicketNodeCard ticket={epic} inferMap={inferMap} onInfer={onInfer} isEpic vsCodeAgents={vsCodeAgents} runningByTicket={runningByTicket} flowConfigMap={flowConfigMap} />
        </NodeErrorBoundary>
        <span className={styles.childrenCount}>{epic.children.length} ticket{epic.children.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Children */}
      {epic.children.length > 0 && (
        <div className={styles.childrenRow}>
          {epic.children.map(child => (
            <div data-role="child-node" key={child.id} className={styles.childNodeWrap}>
              <NodeErrorBoundary adoId={child.ado_id}>
                <TicketNodeCard ticket={child} inferMap={inferMap} onInfer={onInfer} vsCodeAgents={vsCodeAgents} runningByTicket={runningByTicket} flowConfigMap={flowConfigMap} />
              </NodeErrorBoundary>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── TicketGraphView (exportado) ──────────────────────────────────────────────

export default function TicketGraphView({ hierarchy, onSync, isSyncing, syncError, vsCodeAgents = [], runningByTicket = new Map() }) {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  // LLM inference removida: inferMap queda vacío, los handlers son no-op
  // para mantener la firma de props de los componentes hijos sin reescribirlos.
  const inferMap = {};
  const handleInfer = useCallback(() => {}, []);

  // Feature #4 — FlowConfig: cargar reglas una vez y construir map ado_state→agent_type.
  // Mismo patrón que TicketBoard. Keys lowercased para resolución case-insensitive.
  const { data: flowConfigData } = useQuery({
    queryKey: ["flow-config", activeProjectName],
    queryFn: () => FlowConfig.list(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });
  const flowConfigMap = useMemo(() => {
    const map = new Map();
    for (const rule of flowConfigData?.rules ?? []) {
      map.set(rule.ado_state.trim().toLowerCase(), rule.agent_type);
    }
    return map;
  }, [flowConfigData]);

  if (!hierarchy) {
    return <div className={styles.empty}>Sincronizá los tickets primero.</div>;
  }

  const { epics, orphans } = hierarchy;
  const totalTickets = epics.reduce((a, e) => a + 1 + e.children.length, 0) + orphans.length;

  return (
    <div className={styles.graphRoot}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <span className={styles.toolbarCount}>{totalTickets} tickets · {epics.length} épicas</span>
        {/* Error visual de sync */}
        {syncError && (
          <div style={{ color: "#fff", background: "#b91c1c", padding: "6px 12px", borderRadius: 6, margin: "0 12px 0 0", maxWidth: 340, fontSize: 15, fontWeight: 500, display: "inline-block", verticalAlign: "middle" }}>
            <span style={{ marginRight: 8 }}>⚠️</span>
            {syncError}
          </div>
        )}
        <button className={styles.syncBtn} onClick={onSync} disabled={isSyncing}>
          {isSyncing ? "↻ Sincronizando…" : "⟳ Sincronizar ADO"}
        </button>
      </div>

      {/* Épicas con sus hijos */}
      {epics.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>⚡ Épicas</h2>
          <div className={styles.epicsContainer}>
            {epics.map(epic => (
              <EpicGroup
                key={epic.id}
                epic={epic}
                inferMap={inferMap}
                onInfer={handleInfer}
                vsCodeAgents={vsCodeAgents}
                runningByTicket={runningByTicket}
                flowConfigMap={flowConfigMap}
              />
            ))}
          </div>
        </section>
      )}

      {/* Tickets sin épica */}
      {orphans.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>📋 Tickets sin épica</h2>
          <div className={styles.orphansGrid}>
            {orphans.map(t => (
              <NodeErrorBoundary key={t.id} adoId={t.ado_id}>
                <TicketNodeCard
                  ticket={t}
                  inferMap={inferMap}
                  onInfer={handleInfer}
                  vsCodeAgents={vsCodeAgents}
                  runningByTicket={runningByTicket}
                  flowConfigMap={flowConfigMap}
                />
              </NodeErrorBoundary>
            ))}
          </div>
        </section>
      )}

      {totalTickets === 0 && (
        <div className={styles.empty}>No hay tickets. Hacé clic en Sincronizar ADO.</div>
      )}
    </div>
  );
}

import React, { useState, useCallback, useRef, useEffect, useLayoutEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents } from "../api/endpoints";
import { getPinnedAgents } from "../services/preferences";
import styles from "./TicketGraphView.module.css";

// Misma lógica que TicketBoard — infiere tipo de agente desde filename.
function inferType(filename) {
  const f = (filename || "").toLowerCase();
  if (f.includes("business") || f.includes("negocio")) return "business";
  if (f.includes("functional") || f.includes("funcional")) return "functional";
  if (f.includes("technical") || f.includes("tecnic")) return "technical";
  if (f.includes("dev") || f.includes("desarrollador")) return "developer";
  if (f.includes("qa") || f.includes("test")) return "qa";
  return "custom";
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

const LS_KEY = "stacky_pipeline_v1";

// ─── LocalStorage helpers ──────────────────────────────────────────────────────

function lsLoad(ticketId) {
  try {
    const raw = localStorage.getItem(`${LS_KEY}_${ticketId}`);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function lsSave(ticketId, result) {
  try {
    localStorage.setItem(`${LS_KEY}_${ticketId}`, JSON.stringify(result));
  } catch {}
}

function lsLoadAll() {
  const map = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(`${LS_KEY}_`)) {
        const id = parseInt(key.replace(`${LS_KEY}_`, ""));
        if (!isNaN(id)) {
          const v = lsLoad(id);
          if (v) map[id] = v;
        }
      }
    }
  } catch {}
  return map;
}

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

function RunModal({ ticket, mode, suggestedLabel, suggestedFilename, vsCodeAgents, isLaunching, onConfirm, onClose }) {
  const [note, setNote] = useState("");
  const [selectedFilename, setSelectedFilename] = useState(vsCodeAgents[0]?.filename ?? "");
  const canConfirm = mode === "suggested" ? !!suggestedLabel : !!selectedFilename;

  return (
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

        <div className={styles.modalActions}>
          <button className={styles.modalCancel} onClick={onClose} disabled={isLaunching}>Cancelar</button>
          <button
            className={styles.modalConfirm}
            onClick={() => onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : suggestedFilename)}
            disabled={isLaunching || !canConfirm}
          >
            {isLaunching ? "⏳ Abriendo chat…" : "▶ Ejecutar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── PipelineBar ──────────────────────────────────────────────────────────────

function PipelineBar({ summary, isEpic, inferResult, compact = false }) {
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
  const next = inferResult?.next_suggested ?? summary?.next_suggested ?? null;

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

// ─── TicketNode Card ──────────────────────────────────────────────────────────

function TicketNodeCard({ ticket, inferMap, onInfer, isEpic = false, vsCodeAgents = [], runningByTicket = new Map() }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [runModal, setRunModal] = useState(null); // null | "suggested" | "custom"
  const [isLaunching, setIsLaunching] = useState(false);

  const inferResult = inferMap[ticket.id] || null;
  const colors = isEpic ? EPIC_COLORS : (STATE_COLORS[ticket.ado_state] || STATE_COLORS["New"]);
  const summary = isEpic ? epicPipelineSummary(ticket) : ticket.pipeline_summary;
  const next = isEpic ? summary.next_suggested : (inferResult?.next_suggested ?? summary?.next_suggested);
  const nextLabel = next && AGENT_LABELS[next] ? `${AGENT_LABELS[next].icon} ${AGENT_LABELS[next].label}` : null;
  const suggestedFilename = next ? findAgentFilenameByType(next, vsCodeAgents, getPinnedAgents()) : null;
  const isRunning = runningByTicket.has(ticket.id);
  const isClosed = ["Done", "Closed", "Resolved", "Removed", "Completed"].includes(ticket.ado_state);

  const handleLaunch = useCallback(async (note, filename) => {
    setIsLaunching(true);
    try {
      const contextBlocks = note
        ? [{ id: "operator-note", kind: "editable", title: "Nota del operador", content: note }]
        : [];
      await Agents.openChat({ ticket_id: ticket.id, context_blocks: contextBlocks, vscode_agent_filename: filename ?? undefined });
      qc.invalidateQueries({ queryKey: ["executions-active"] });
      qc.invalidateQueries({ queryKey: ["executions-queued"] });
      setRunModal(null);
    } finally {
      setIsLaunching(false);
    }
  }, [ticket.id, qc]);

  return (
    <>
      <div
        className={`${styles.nodeCard} ${isEpic ? styles.epicCard : ""} ${expanded ? styles.nodeExpanded : ""} ${isRunning ? styles.nodeRunning : ""}`}
        style={{ background: colors.bg, borderColor: isRunning ? "#22c55e" : colors.border }}
        onClick={() => setExpanded(x => !x)}
      >
        {isRunning && (
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
            {/* Botón Run compacto siempre visible en no-épicas */}
            {!isEpic && !isClosed && (
              <button
                className={styles.runBtnCompact}
                title={nextLabel ? `Run sugerido: ${nextLabel}` : "Run personalizado"}
                onClick={e => { e.stopPropagation(); setRunModal(next ? "suggested" : "custom"); }}
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
          />

          {/* Next agent prominente */}
          {next && !isEpic && (
            <div className={styles.nextAgentRow} onClick={e => e.stopPropagation()}>
              <span className={styles.nextAgentLabel}>
                Próximo: {AGENT_LABELS[next]?.icon} <strong style={{ color: "#fbbf24" }}>{AGENT_LABELS[next]?.label}</strong>
              </span>
              {!inferResult && (
                <button
                  className={styles.inferBtn}
                  onClick={e => { e.stopPropagation(); onInfer(ticket.id, false); }}
                >
                  🤖 Inferir
                </button>
              )}
            </div>
          )}
          {!inferResult && !isEpic && (
            <div className={styles.inferRowInline} onClick={e => e.stopPropagation()}>
              <button
                className={styles.inferBtnSmall}
                onClick={e => { e.stopPropagation(); onInfer(ticket.id, false); }}
              >
                🤖 Inferir estado
              </button>
            </div>
          )}
        </div>

        {/* Expandido */}
        {expanded && (
          <div className={styles.nodeBody} onClick={e => e.stopPropagation()}>
            {inferResult && !isEpic && (
              <>
                <PipelineBar summary={summary} isEpic={false} inferResult={inferResult} />
                <p className={styles.inferSummary}>{inferResult.summary}</p>
                <div className={styles.inferMeta}>
                  <span>{inferResult.source === "cache" ? "⚡ cache" : "🤖 LLM"} · {inferResult.model_used}</span>
                  <button className={styles.refreshBtn} onClick={() => onInfer(ticket.id, true)}>⟳ Refrescar</button>
                </div>
              </>
            )}
            {ticket.description && (
              <p className={styles.nodeDesc}>{ticket.description.slice(0, 300)}{ticket.description.length > 300 ? "…" : ""}</p>
            )}
            {ticket.ado_url && (
              <a className={styles.adoLink} href={ticket.ado_url} target="_blank" rel="noreferrer">
                Abrir en ADO ↗
              </a>
            )}

            {/* Botones Run expandidos */}
            {!isEpic && !isClosed && (
              <div className={styles.runButtons}>
                <button
                  className={styles.runSuggestedBtn}
                  disabled={!next}
                  onClick={() => setRunModal("suggested")}
                  title={nextLabel ? `Correr: ${nextLabel}` : "Esperando inferencia…"}
                >
                  ▶ Run Sugerido
                  {nextLabel && <span className={styles.runBtnHint}>{nextLabel}</span>}
                </button>
                <button
                  className={styles.runCustomBtn}
                  onClick={() => setRunModal("custom")}
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

function EpicGroup({ epic, inferMap, onInfer, vsCodeAgents, runningByTicket }) {
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
        <TicketNodeCard ticket={epic} inferMap={inferMap} onInfer={onInfer} isEpic vsCodeAgents={vsCodeAgents} runningByTicket={runningByTicket} />
        <span className={styles.childrenCount}>{epic.children.length} ticket{epic.children.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Children */}
      {epic.children.length > 0 && (
        <div className={styles.childrenRow}>
          {epic.children.map(child => (
            <div data-role="child-node" key={child.id} className={styles.childNodeWrap}>
              <TicketNodeCard ticket={child} inferMap={inferMap} onInfer={onInfer} vsCodeAgents={vsCodeAgents} runningByTicket={runningByTicket} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── TicketGraphView (exportado) ──────────────────────────────────────────────

export default function TicketGraphView({ hierarchy, onSync, isSyncing, syncError, vsCodeAgents = [], runningByTicket = new Map() }) {
  const qc = useQueryClient();

  // Cargar inferencias previas desde localStorage al montar
  const [inferMap, setInferMap] = useState(() => lsLoadAll());
  const [loadingIds, setLoadingIds] = useState(new Set());

  const inferMutation = useMutation({
    mutationFn: ({ ticketId, force }) => Tickets.adoPipelineStatus(ticketId, force),
    onSuccess: (data, { ticketId }) => {
      lsSave(ticketId, data);
      setInferMap(prev => ({ ...prev, [ticketId]: data }));
      setLoadingIds(prev => { const s = new Set(prev); s.delete(ticketId); return s; });
    },
    onError: (_, { ticketId }) => {
      setLoadingIds(prev => { const s = new Set(prev); s.delete(ticketId); return s; });
    },
  });

  const handleInfer = useCallback((ticketId, force) => {
    setLoadingIds(prev => new Set([...prev, ticketId]));
    inferMutation.mutate({ ticketId, force });
  }, [inferMutation]);

  const handleInferAll = useCallback(() => {
    const allTickets = [
      ...(hierarchy?.epics?.flatMap(e => e.children) || []),
      ...(hierarchy?.orphans || []),
    ];
    allTickets.forEach(t => {
      if (!inferMap[t.id]) {
        setTimeout(() => handleInfer(t.id, false), Math.random() * 2000);
      }
    });
  }, [hierarchy, inferMap, handleInfer]);

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
        <button className={styles.inferAllBtn} onClick={handleInferAll}>
          🤖 Inferir pendientes
        </button>
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
              <TicketNodeCard
                key={t.id}
                ticket={t}
                inferMap={inferMap}
                onInfer={handleInfer}
                vsCodeAgents={vsCodeAgents}
                runningByTicket={runningByTicket}
              />
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

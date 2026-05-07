import React, { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, Executions } from "../api/endpoints";
import type { Ticket, TicketNode, TicketHierarchy, PipelineInferenceResult, AgentExecution, VsCodeAgent } from "../types";
import PipelineStatus from "../components/PipelineStatus";
import TicketGraphView from "../components/TicketGraphView";
import { useRunningStatus } from "../hooks/useRunningStatus";
import { getPinnedAgents } from "../services/preferences";
import styles from "./TicketBoard.module.css";

// Infiere el tipo de agente desde el filename — misma lógica que EmployeeCard.
function inferType(filename: string): string {
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
  onConfirm: (note: string, filename: string | null) => void;
  onClose: () => void;
}

function RunModal({ ticket, mode, suggestedLabel, suggestedFilename, vsCodeAgents, isLaunching, onConfirm, onClose }: RunModalProps) {
  const [note, setNote] = useState("");
  const [selectedFilename, setSelectedFilename] = useState<string>(vsCodeAgents[0]?.filename ?? "");

  const canConfirm = mode === "suggested"
    ? !!suggestedLabel
    : !!selectedFilename;

  return (
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

        <div className={styles.modalActions}>
          <button className={styles.modalCancel} onClick={onClose} disabled={isLaunching}>
            Cancelar
          </button>
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

// ─── TicketCard ───────────────────────────────────────────────────────────────

interface TicketCardProps {
  ticket: Ticket;
  runningExecution: AgentExecution | null;
  vsCodeAgents: VsCodeAgent[];
  indent?: boolean;
}

function TicketCard({ ticket, runningExecution, vsCodeAgents, indent }: TicketCardProps) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [runModal, setRunModal] = useState<"suggested" | "custom" | null>(null);
  const [isLaunching, setIsLaunching] = useState(false);

  const inferenceKey = ["ado-pipeline", ticket.id];

  const { data: inference, isFetching, isError } = useQuery<PipelineInferenceResult>({
    queryKey: inferenceKey,
    queryFn: () => Tickets.adoPipelineStatus(ticket.id),
    staleTime: 55 * 60 * 1000,
    retry: false,
    enabled: false,
  });

  const inferMutation = useMutation({
    mutationFn: (force: boolean) => Tickets.adoPipelineStatus(ticket.id, force),
    onSuccess: (data) => {
      qc.setQueryData(inferenceKey, data);
    },
  });

  const handleRefresh = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    inferMutation.mutate(true);
  }, [inferMutation]);

  // Auto-trigger inference when card first expands and no result exists yet
  useEffect(() => {
    if (expanded && !result && !inferMutation.isPending && !isFetching) {
      inferMutation.mutate(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded]);

  const isLoading = isFetching || inferMutation.isPending;
  const result = inference ?? (inferMutation.data ?? null);
  const nextSuggested = result?.next_suggested ?? null;
  const nextLabel = nextSuggested ? (NEXT_AGENT_LABELS[nextSuggested] ?? nextSuggested) : null;

  // Resuelve el filename del agente del equipo que corresponde al tipo sugerido.
  // Prioriza agentes pinneados ("Tu Equipo") sobre cualquier agente disponible.
  const suggestedFilename = nextSuggested
    ? findAgentFilenameByType(nextSuggested, vsCodeAgents, getPinnedAgents())
    : null;

  const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "");
  // Fuente dual: AgentExecution activa (prop) O stacky_status del ticket (BD)
  const isRunning = !isClosed && (!!runningExecution || ticket.stacky_status === "running");
  const runningAgentType = runningExecution?.agent_type ?? null;

  const handleRunConfirm = useCallback(async (note: string, filename: string | null) => {
    setIsLaunching(true);
    try {
      const contextBlocks = note
        ? [{ id: "operator-note", kind: "editable" as const, title: "Nota del operador", content: note }]
        : [];
      await Agents.openChat({
        ticket_id: ticket.id,
        context_blocks: contextBlocks,
        vscode_agent_filename: filename ?? undefined,
      });
      setRunModal(null);
    } finally {
      setIsLaunching(false);
    }
  }, [ticket.id]);

  return (
    <>
      <div className={`${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""} ${indent ? styles.cardIndented : ""}`}>

        {/* Banner de ejecución activa */}
        {isRunning && (
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

          {result && !expanded && (
            <div className={styles.pipelineInline}>
              <PipelineStatus result={result} compact />
            </div>
          )}

          <div className={styles.cardActions} onClick={(e) => e.stopPropagation()}>
            {isLoading && <span className={styles.inferring}>⏳ Analizando…</span>}
            {result && !isLoading && (
              <>
                {nextLabel && <span className={styles.nextTag}>→ {nextLabel}</span>}
                <button className={styles.refreshBtn} onClick={handleRefresh} title="Re-inferir ignorando cache">⟳</button>
              </>
            )}
            {isError && <span className={styles.errorTag}>⚠ Error al inferir</span>}
          </div>
        </div>

        {/* Detalle expandido */}
        {expanded && (
          <div className={styles.cardBody}>
            {result ? (
              <PipelineStatus result={result} />
            ) : (
              <div className={styles.noInference}>
                {isLoading ? "Consultando ADO + LLM…" : "Analizando pipeline…"}
              </div>
            )}

            {/* Botones de ejecución */}
            <div className={styles.runButtons}>
              <button
                className={styles.runSuggestedBtn}
                onClick={(e) => { e.stopPropagation(); setRunModal("suggested"); }}
                disabled={!nextSuggested || isRunning}
                title={
                  isRunning
                    ? "Hay un agente corriendo sobre este ticket — esperá a que termine"
                    : nextSuggested
                    ? `Correr agente sugerido: ${nextLabel}`
                    : "Esperando inferencia de pipeline…"
                }
              >
                ▶ Run Sugerido
                {nextLabel && <span className={styles.runBtnHint}>{nextLabel}</span>}
              </button>
              <button
                className={styles.runCustomBtn}
                onClick={(e) => { e.stopPropagation(); setRunModal("custom"); }}
                disabled={isRunning}
                title={isRunning ? "Hay un agente corriendo sobre este ticket" : undefined}
              >
                ⚙ Run Custom
              </button>
            </div>

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
}

function EpicGroup({ epic, runningByTicket, vsCodeAgents }: EpicGroupProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const isClosed = CLOSED_STATES.includes(epic.ado_state ?? "");
  const runningExec = runningByTicket.get(epic.id) ?? null;
  const isRunning = !isClosed && !!runningExec;
  const functionalFilename = findAgentFilenameByType("functional", vsCodeAgents, getPinnedAgents());

  const handleRunFunctional = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!functionalFilename) return;
    setIsLaunching(true);
    try {
      await Agents.openChat({
        ticket_id: epic.id,
        context_blocks: [],
        vscode_agent_filename: functionalFilename,
      });
    } finally {
      setIsLaunching(false);
    }
  }, [epic.id, functionalFilename]);

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
  const [search, setSearch] = useState("");
  const [onlyPending, setOnlyPending] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("tree");

  // Hook centralizado de estado running (fuente dual: stacky_status + executions polling)
  const { runningByTicket, runningTicketIds, getRunningTickets } = useRunningStatus();

  const { data: tickets, isLoading } = useQuery<Ticket[]>({
    queryKey: ["tickets"],
    queryFn: Tickets.list,
    refetchInterval: 60_000,
  });

  const { data: hierarchy, isLoading: isHierarchyLoading } = useQuery<TicketHierarchy>({
    queryKey: ["tickets-hierarchy"],
    queryFn: Tickets.hierarchy,
    refetchInterval: 60_000,
    enabled: viewMode === "tree" || viewMode === "graph",
  });

  // VsCode agents para el dropdown de Run Custom
  const { data: vsCodeAgents } = useQuery<VsCodeAgent[]>({
    queryKey: ["vscode-agents"],
    queryFn: Agents.vsCodeAgents,
    staleTime: 5 * 60 * 1000,
  });

  // Estado de error para mostrar feedback de sync
  const [syncError, setSyncError] = useState<string | null>(null);
  const syncMutation = useMutation({
    mutationFn: Tickets.sync,
    onSuccess: () => {
      setSyncError(null);
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
    },
    onError: (err: any) => {
      // err puede ser Error lanzado por api.client.ts
      let msg = "Error al sincronizar con ADO.";
      if (err && typeof err.message === "string") {
        msg = err.message;
      }
      setSyncError(msg);
    },
  });

  // Filtrado para vista jerárquica (filtra dentro de epics + orphans)
  function filterNode(node: TicketNode): boolean {
    if (search) {
      const q = search.toLowerCase();
      const selfMatch = node.title.toLowerCase().includes(q) || String(node.ado_id).includes(q);
      const childMatch = node.children.some((c) => filterNode(c));
      if (!selfMatch && !childMatch) return false;
    }
    if (onlyPending && CLOSED_STATES.includes(node.ado_state ?? "")) return false;
    return true;
  }

  const filteredEpics = (hierarchy?.epics ?? []).filter(filterNode);
  const filteredOrphans = (hierarchy?.orphans ?? []).filter((n) => filterNode(n as TicketNode));
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
          {viewMode === "graph" && hierarchy && (
            <span className={styles.count}>
              {hierarchy.epics.length} épicas · {hierarchy.epics.reduce((a, e) => a + e.children.length, 0) + hierarchy.orphans.length} tareas
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
          <label className={styles.filterToggle}>
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
            />
            Solo abiertos
          </label>
          {/* Error visual de sync */}
          {syncError && (
            <div style={{ color: "#fff", background: "#b91c1c", padding: "6px 12px", borderRadius: 6, marginBottom: 8, maxWidth: 340, fontSize: 15, fontWeight: 500 }}>
              <span style={{ marginRight: 8 }}>⚠️</span>
              {syncError}
            </div>
          )}
          <button
            className={styles.syncBtn}
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            title="Sincronizar tickets desde ADO"
          >
            {syncMutation.isPending ? "↻ Sincronizando…" : "⟳ Sincronizar ADO"}
          </button>
        </div>
      </header>

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
                hierarchy={hierarchy ?? null}
                onSync={() => syncMutation.mutate()}
                isSyncing={syncMutation.isPending}
                syncError={syncError}
                vsCodeAgents={vsCodeAgents ?? []}
                runningByTicket={runningByTicket}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

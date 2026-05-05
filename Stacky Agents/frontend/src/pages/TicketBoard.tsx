import React, { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tickets, Agents, Executions } from "../api/endpoints";
import type { Ticket, PipelineInferenceResult, AgentExecution, VsCodeAgent } from "../types";
import PipelineStatus from "../components/PipelineStatus";
import styles from "./TicketBoard.module.css";

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
  vsCodeAgents: VsCodeAgent[];
  isLaunching: boolean;
  onConfirm: (note: string, filename: string | null) => void;
  onClose: () => void;
}

function RunModal({ ticket, mode, suggestedLabel, vsCodeAgents, isLaunching, onConfirm, onClose }: RunModalProps) {
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
            <span className={styles.modalAgentHint}>agente sugerido por inferencia</span>
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
            onClick={() => onConfirm(note.trim(), mode === "custom" ? selectedFilename || null : null)}
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
}

function TicketCard({ ticket, runningExecution, vsCodeAgents }: TicketCardProps) {
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

  const isLoading = isFetching || inferMutation.isPending;
  const result = inference ?? (inferMutation.data ?? null);
  const nextSuggested = result?.next_suggested ?? null;
  const nextLabel = nextSuggested ? (NEXT_AGENT_LABELS[nextSuggested] ?? nextSuggested) : null;

  const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "");
  const isRunning = !!runningExecution && !isClosed;

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
      <div className={`${styles.card} ${expanded ? styles.cardExpanded : ""} ${isRunning ? styles.cardRunning : ""}`}>

        {/* Banner de ejecución activa */}
        {isRunning && (
          <div className={styles.runningCardBanner}>
            <span className={styles.runningPulse} />
            <span>EN EJECUCIÓN</span>
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
                disabled={!nextSuggested}
                title={nextSuggested ? `Correr agente sugerido: ${nextLabel}` : "Esperando inferencia de pipeline…"}
              >
                ▶ Run Sugerido
                {nextLabel && <span className={styles.runBtnHint}>{nextLabel}</span>}
              </button>
              <button
                className={styles.runCustomBtn}
                onClick={(e) => { e.stopPropagation(); setRunModal("custom"); }}
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
          vsCodeAgents={vsCodeAgents}
          isLaunching={isLaunching}
          onConfirm={handleRunConfirm}
          onClose={() => setRunModal(null)}
        />
      )}
    </>
  );
}

// ─── TicketBoard (página principal) ──────────────────────────────────────────

export default function TicketBoard() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [onlyPending, setOnlyPending] = useState(false);

  const { data: tickets, isLoading } = useQuery<Ticket[]>({
    queryKey: ["tickets"],
    queryFn: Tickets.list,
    refetchInterval: 60_000,
  });

  // Polling de ejecuciones activas cada 5 segundos
  const { data: activeExecs } = useQuery<AgentExecution[]>({
    queryKey: ["executions-active"],
    queryFn: () => Executions.list({ status: "running" }),
    refetchInterval: 5_000,
    staleTime: 0,
  });

  const { data: queuedExecs } = useQuery<AgentExecution[]>({
    queryKey: ["executions-queued"],
    queryFn: () => Executions.list({ status: "queued" }),
    refetchInterval: 5_000,
    staleTime: 0,
  });

  // VsCode agents para el dropdown de Run Custom
  const { data: vsCodeAgents } = useQuery<VsCodeAgent[]>({
    queryKey: ["vscode-agents"],
    queryFn: Agents.vsCodeAgents,
    staleTime: 5 * 60 * 1000,
  });

  const syncMutation = useMutation({
    mutationFn: Tickets.sync,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tickets"] }),
  });

  const batchInferMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await Tickets.adoPipelineBatch(ids, false);
      Object.entries(res.results).forEach(([tid, result]) => {
        if (!("error" in result)) {
          qc.setQueryData(["ado-pipeline", parseInt(tid)], result);
        }
      });
      return res;
    },
  });

  // Auto-infer: al cargar/recargar tickets, inferir solo los que no tienen cache
  useEffect(() => {
    if (!tickets || tickets.length === 0 || batchInferMutation.isPending) return;
    const pending = tickets.filter((t) => {
      const hasCached = qc.getQueryData(["ado-pipeline", t.id]) != null;
      const isClosed = CLOSED_STATES.includes(t.ado_state ?? "");
      return !hasCached && !isClosed;
    });
    if (pending.length === 0) return;
    batchInferMutation.mutate(pending.map((t) => t.id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickets]);

  const filtered = (tickets ?? []).filter((t) => {
    if (search) {
      const q = search.toLowerCase();
      if (!t.title.toLowerCase().includes(q) && !String(t.ado_id).includes(q)) return false;
    }
    if (onlyPending) {
      if (CLOSED_STATES.includes(t.ado_state ?? "")) return false;
    }
    return true;
  });

  // Map ticketId -> running execution
  const runningByTicket = new Map<number, AgentExecution>();
  [...(activeExecs ?? []), ...(queuedExecs ?? [])].forEach((e) => {
    if (!runningByTicket.has(e.ticket_id)) {
      runningByTicket.set(e.ticket_id, e);
    }
  });

  // Tickets activos (no cerrados) con ejecución en curso
  const runningTickets = (tickets ?? []).filter(
    (t) => runningByTicket.has(t.id) && !CLOSED_STATES.includes(t.ado_state ?? "")
  );

  return (
    <div className={styles.root}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>📋</span>
          <h1 className={styles.title}>Tickets ADO</h1>
          {tickets && (
            <span className={styles.count}>{filtered.length} de {tickets.length}</span>
          )}
          {batchInferMutation.isPending && (
            <span className={styles.autoInferBadge}>⏳ Analizando pipeline…</span>
          )}
        </div>
        <div className={styles.headerActions}>
          <label className={styles.filterToggle}>
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
            />
            Solo abiertos
          </label>
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
            {runningTickets.map((t) => (
              <span key={t.id} className={styles.activeExecChip}>
                ADO-{t.ado_id}
                <span className={styles.activeExecChipTitle}>{t.title.slice(0, 30)}{t.title.length > 30 ? "…" : ""}</span>
              </span>
            ))}
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
        {isLoading && <div className={styles.loading}>Cargando tickets…</div>}
        {!isLoading && filtered.length === 0 && (
          <div className={styles.empty}>
            No hay tickets. Hacé clic en «Sincronizar ADO».
          </div>
        )}
        <div className={styles.grid}>
          {filtered.map((t) => (
            <TicketCard
              key={t.id}
              ticket={t}
              runningExecution={runningByTicket.get(t.id) ?? null}
              vsCodeAgents={vsCodeAgents ?? []}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

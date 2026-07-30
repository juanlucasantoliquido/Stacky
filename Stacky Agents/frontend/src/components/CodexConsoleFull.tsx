/**
 * Plan 265 — Consola en pantalla completa: la MISMA sesión que el dock, otra
 * presentación. Este componente NO tiene su propio stream: recibe las líneas,
 * el estado de la ejecución y los callbacks de CodexConsoleDock, que es quien
 * sigue montando `useExecutionStream` (una sola sesión, dos presentaciones).
 *
 * Paneles laterales (Contexto / Repositorio / Historial), búsqueda, render
 * rico y acciones (cancelar / volver a lanzar) están todos gateados por sus
 * flags propias y degradan con un motivo visible ante cualquier problema.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import { Ban, ChevronLeft, ChevronRight, Copy, FolderGit2, History as HistoryIcon, Info, RotateCcw, Search, Shrink, X } from "lucide-react";

import { Agents, Console, Executions, GitReadonly } from "../api/endpoints";
import type { AgentExecution, LogLine } from "../types";
import { readCachedBoolFlag } from "../services/flagGate";
import { useConfirm } from "./ui";
import { copyText } from "../services/copyService";
import { formatLoadErrorMessage } from "../utils/loadError";
import { groupLinesIntoChunks, isCommandChunk } from "../services/consoleRender";
import { normalizeRuntime, capabilitiesFor } from "../services/consoleCapabilities";
import { availableActions, requiresConfirmation, confirmationText } from "../services/consoleActions";
import { searchLines, nextHit, prevHit } from "../services/consoleSearch";
import { groupFilesByStatus, shortPath } from "../services/consoleRepoPanel";
import { historyPanelState } from "../services/consoleHistoryPanel";
import styles from "./CodexConsoleFull.module.css";

type SidePanelId = "contexto" | "repositorio" | "historial" | null;

export interface CodexConsoleFullProps {
  executionId: number;
  lines: LogLine[];
  dropped: number;
  done: boolean;
  execution: AgentExecution | undefined;
  runtimeLabel: string;
  totalTokens: number;
  onBackToDock: () => void;
  onOpenExecution: (id: number) => void;
  /** Incrementado por CodexConsoleDock ante Ctrl+Shift+F: pone el foco acá. */
  focusSearchRequestId: number;
}

export default function CodexConsoleFull(props: CodexConsoleFullProps) {
  const {
    executionId, lines, dropped, done, execution, runtimeLabel, totalTokens,
    onBackToDock, onOpenExecution, focusSearchRequestId,
  } = props;

  const qc = useQueryClient();
  const askConfirm = useConfirm();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  const [sidePanel, setSidePanel] = useState<SidePanelId>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentHit, setCurrentHit] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  // flagGate (197 §6.1): lectura cacheada, fail-open ON — la misma fuente
  // única de lectura de flags que usa el resto del frontend.
  const richRenderOn = readCachedBoolFlag("STACKY_CONSOLE_RICH_RENDER_ENABLED");
  const repoPanelOn = readCachedBoolFlag("STACKY_CONSOLE_REPO_PANEL_ENABLED");

  const status = execution?.status ?? null;
  const runtime = normalizeRuntime(execution?.metadata?.runtime ?? null);
  const hasOrigin = Boolean(execution?.ticket_id && execution?.agent_type);
  const capabilities = capabilitiesFor(runtime, { hasOrigin });
  const actions = availableActions({ status, runtime: execution?.metadata?.runtime as string ?? null, hasOrigin });
  const cancelAction = actions.find((a) => a.id === "cancel");
  const relaunchAction = actions.find((a) => a.id === "relaunch");

  // ── Búsqueda (F5c) — puramente sobre las líneas ya en memoria ─────────────
  const hits = useMemo(() => searchLines(lines, searchQuery), [lines, searchQuery]);
  useEffect(() => {
    setCurrentHit(hits.length > 0 ? 0 : null);
  }, [searchQuery, hits.length]);

  // Ctrl+Shift+F (CodexConsoleDock) incrementa focusSearchRequestId: foco acá.
  useEffect(() => {
    if (focusSearchRequestId > 0) searchInputRef.current?.focus();
  }, [focusSearchRequestId]);

  // ── Render (F2) ────────────────────────────────────────────────────────────
  const chunks = useMemo(() => groupLinesIntoChunks(lines), [lines]);

  // ── Cancelar / volver a lanzar (F3) ────────────────────────────────────────
  const cancelMutation = useMutation({
    mutationFn: () => Executions.cancel(executionId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["codex-console-execution", executionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });

  const relaunchMutation = useMutation({
    mutationFn: () => {
      if (!execution) throw new Error("sin datos de la ejecución");
      return Agents.run({
        agent_type: execution.agent_type,
        ticket_id: execution.ticket_id,
        context_blocks: execution.input_context ?? [],
        project: execution.project ?? undefined,
      });
    },
    onSuccess: (res) => onOpenExecution(res.execution_id),
  });

  const handleCancel = async () => {
    if (!cancelAction?.enabled) return;
    const confirmed = requiresConfirmation("cancel")
      ? await askConfirm({
          title: "Cancelar ejecución",
          message: confirmationText("cancel", executionId),
          tone: "danger",
          confirmLabel: "Cancelar ejecución",
          cancelLabel: "Volver",
        })
      : true;
    if (confirmed) cancelMutation.mutate();
  };

  const handleCopyAll = async () => {
    const text = lines.map((l) => l.message ?? "").join("\n");
    await copyText(text);
  };

  // ── Escape local (D3, F6): lo maneja el contenedor, NUNCA el registro global ──
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onBackToDock();
    }
  };

  return (
    <section className={styles.full} aria-label={`Consola ${runtimeLabel} en pantalla completa`} onKeyDown={handleKeyDown}>
      <header className={styles.fullHeader}>
        <div className={styles.headerLeft}>
          <div className={styles.title}>
            <span>{runtimeLabel}</span>
            <span className={styles.badge}>#{executionId}</span>
            <span className={`${styles.badge} ${done ? styles.badgeDone : styles.badgeRunning}`}>
              {status ?? "—"}
            </span>
            {totalTokens > 0 && <span className={styles.badge}>⎁ {totalTokens.toLocaleString()}</span>}
          </div>
          <span className={styles.modelEffortSlot} data-slot="model-effort">
            {capabilities.modelEffortSlot.note ?? "—"}
          </span>
        </div>

        <div className={styles.searchBar}>
          <Search size={14} />
          <input
            ref={searchInputRef}
            className={styles.searchInput}
            placeholder="Buscar en la conversación (Ctrl+Shift+F)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                setCurrentHit((cur) => (e.shiftKey ? prevHit(hits, cur) : nextHit(hits, cur)));
              }
            }}
          />
          <span className={styles.searchHits}>
            {hits.length > 0 ? `${(currentHit ?? 0) + 1}/${hits.length}` : searchQuery ? "0/0" : ""}
          </span>
          <button
            type="button"
            className={styles.iconButton}
            disabled={hits.length === 0}
            onClick={() => setCurrentHit((cur) => prevHit(hits, cur))}
            title="Resultado anterior"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            type="button"
            className={styles.iconButton}
            disabled={hits.length === 0}
            onClick={() => setCurrentHit((cur) => nextHit(hits, cur))}
            title="Resultado siguiente (Enter)"
          >
            <ChevronRight size={14} />
          </button>
        </div>

        <div className={styles.headerRight}>
          <button type="button" className={styles.iconButton} onClick={() => { void handleCopyAll(); }} title="Copiar toda la conversación (Ctrl+Shift+C)">
            <Copy size={14} /> Copiar todo
          </button>
          <button
            type="button"
            className={styles.iconButton}
            disabled={!relaunchAction?.enabled || relaunchMutation.isPending}
            title={relaunchAction?.reason ?? "Volver a lanzar"}
            onClick={() => relaunchMutation.mutate()}
          >
            <RotateCcw size={14} /> Volver a lanzar
          </button>
          <button
            type="button"
            className={styles.dangerButton}
            disabled={!cancelAction?.enabled || cancelMutation.isPending}
            title={cancelAction?.reason ?? "Cancelar"}
            onClick={() => { void handleCancel(); }}
          >
            <Ban size={14} /> Cancelar
          </button>
          <button
            type="button"
            className={`${styles.iconButton} ${sidePanel === "contexto" ? styles.sideTabActive : ""}`}
            onClick={() => setSidePanel((p) => (p === "contexto" ? null : "contexto"))}
            title="Panel de contexto"
          >
            <Info size={14} />
          </button>
          {repoPanelOn && (
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setSidePanel((p) => (p === "repositorio" ? null : "repositorio"))}
              title="Panel de repositorio"
            >
              <FolderGit2 size={14} />
            </button>
          )}
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => setSidePanel((p) => (p === "historial" ? null : "historial"))}
            title="Historial de sesiones"
          >
            <HistoryIcon size={14} />
          </button>
          <button type="button" className={styles.iconButton} onClick={onBackToDock} title="Volver a la barra (Ctrl+Shift+Enter o Escape)">
            <Shrink size={14} /> Dock
          </button>
        </div>
      </header>

      {cancelMutation.isError && (
        <div className={styles.maskedNotice} role="alert">
          No se pudo cancelar: {formatLoadErrorMessage(cancelMutation.error)}
        </div>
      )}

      <div className={styles.main}>
        <div className={styles.body} ref={bodyRef}>
          {dropped > 0 && (
            <div className={styles.droppedNotice} role="status">
              Se descartaron {dropped} líneas más antiguas (límite del buffer en memoria).
            </div>
          )}
          {richRenderOn
            ? chunks.map((chunk, i) =>
                chunk.kind === "code" ? (
                  <div key={i} className={styles.chunkCode}>
                    {chunk.copyable && (
                      <button
                        type="button"
                        className={styles.copyChunkButton}
                        onClick={() => { void copyText(chunk.content); }}
                        title={isCommandChunk(chunk) ? "Copiar comando" : "Copiar bloque"}
                      >
                        <Copy size={11} /> copiar
                      </button>
                    )}
                    <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                      {`\`\`\`${chunk.lang ?? ""}\n${chunk.content}\n\`\`\``}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div key={i} className={styles.chunkText}>
                    <ReactMarkdown>{chunk.content}</ReactMarkdown>
                  </div>
                ),
              )
            : lines.map((line, i) => (
                <div key={i} className={styles.chunkText}>
                  {line.message}
                </div>
              ))}
        </div>

        {sidePanel && (
          <aside className={styles.sidePanel}>
            <div className={styles.sideTabs}>
              <button
                type="button"
                className={`${styles.sideTab} ${sidePanel === "contexto" ? styles.sideTabActive : ""}`}
                onClick={() => setSidePanel("contexto")}
              >
                Contexto
              </button>
              {repoPanelOn && (
                <button
                  type="button"
                  className={`${styles.sideTab} ${sidePanel === "repositorio" ? styles.sideTabActive : ""}`}
                  onClick={() => setSidePanel("repositorio")}
                >
                  Repositorio
                </button>
              )}
              <button
                type="button"
                className={`${styles.sideTab} ${sidePanel === "historial" ? styles.sideTabActive : ""}`}
                onClick={() => setSidePanel("historial")}
              >
                Historial
              </button>
              <button type="button" className={styles.iconButton} onClick={() => setSidePanel(null)} title="Cerrar panel">
                <X size={13} />
              </button>
            </div>
            <div className={styles.sideBody}>
              {sidePanel === "contexto" && (
                <ContextPanel execution={execution} runtimeLabel={runtimeLabel} dropped={dropped} capabilityNote={capabilities.cancel.note} />
              )}
              {sidePanel === "repositorio" && repoPanelOn && (
                <RepoPanel project={execution?.project ?? null} selectedFile={selectedFile} onSelectFile={setSelectedFile} />
              )}
              {sidePanel === "historial" && <HistoryPanel onOpenExecution={onOpenExecution} />}
            </div>
          </aside>
        )}
      </div>
    </section>
  );
}

// ── Panel Contexto (F5a) — todo de datos que ya existen ──────────────────────
function ContextPanel({
  execution,
  runtimeLabel,
  dropped,
  capabilityNote,
}: {
  execution: AgentExecution | undefined;
  runtimeLabel: string;
  dropped: number;
  capabilityNote: string | null;
}) {
  return (
    <div>
      <div className={styles.contextRow}>
        <span className={styles.contextLabel}>Proyecto</span>
        <span>{execution?.project ?? "—"}</span>
      </div>
      <div className={styles.contextRow}>
        <span className={styles.contextLabel}>Herramienta</span>
        <span>{runtimeLabel}</span>
      </div>
      <div className={styles.contextRow}>
        <span className={styles.contextLabel}>Estado</span>
        <span>{execution?.status ?? "—"}</span>
      </div>
      <div className={styles.contextRow}>
        <span className={styles.contextLabel}>Ticket</span>
        <span>{execution?.ticket_id ?? "—"}</span>
      </div>
      <div className={styles.contextRow}>
        <span className={styles.contextLabel}>Líneas descartadas</span>
        <span>{dropped}</span>
      </div>
      {capabilityNote && (
        <div className={styles.contextRow}>
          <span className={styles.contextLabel}>Cancelación</span>
          <span>{capabilityNote}</span>
        </div>
      )}
    </div>
  );
}

// ── Panel Repositorio (F4) — SOLO LECTURA ────────────────────────────────────
function RepoPanel({
  project,
  selectedFile,
  onSelectFile,
}: {
  project: string | null;
  selectedFile: string | null;
  onSelectFile: (path: string | null) => void;
}) {
  const workspace = project ?? "";
  const statusQ = useQuery({
    queryKey: ["console-repo-status", workspace],
    queryFn: () => GitReadonly.status(workspace),
    enabled: workspace.length > 0,
  });
  const diffQ = useQuery({
    queryKey: ["console-repo-diff", workspace, selectedFile],
    queryFn: () => GitReadonly.diff(workspace, selectedFile as string),
    enabled: workspace.length > 0 && selectedFile != null,
  });

  const statusBody = statusQ.data?.data ?? null; // RawResponse<T>.data — solo poblado en 2xx
  const diffBody = diffQ.data?.data ?? null;

  if (!workspace) return <div className={styles.emptyState}>Sin workspace registrado para este proyecto.</div>;
  if (statusQ.isLoading) return <div className={styles.emptyState}>Cargando…</div>;
  if (!statusQ.data?.ok || !statusBody?.available) {
    return (
      <div className={styles.emptyState}>
        {statusBody?.reason ?? statusQ.data?.errorBody?.message ?? "El panel de repositorio no está disponible."}
      </div>
    );
  }

  const grouped = groupFilesByStatus(statusBody.files);
  const groups: Array<[string, typeof statusBody.files]> = [
    ["Modificados", grouped.modified],
    ["Nuevos", grouped.new],
    ["Borrados", grouped.deleted],
    ["Sin seguimiento", grouped.untracked],
    ["Otros", grouped.otros],
  ];

  return (
    <div>
      {groups.every(([, arr]) => arr.length === 0) && <div className={styles.emptyState}>Sin cambios.</div>}
      {groups.map(([label, files]) =>
        files.length === 0 ? null : (
          <div key={label}>
            <div className={styles.groupLabel}>{label}</div>
            {files.map((f) => (
              <button key={f.path} type="button" className={styles.fileRow} onClick={() => onSelectFile(f.path)}>
                <span className={styles.fileStatus}>{f.status}</span>
                <span>{shortPath(f.path, 42)}</span>
              </button>
            ))}
          </div>
        ),
      )}
      {selectedFile && (
        <>
          <div className={styles.groupLabel}>Diferencias — {shortPath(selectedFile, 42)}</div>
          {diffBody?.ok && diffBody.available ? (
            <>
              {(diffBody.masked ?? 0) > 0 && (
                <div className={styles.maskedNotice}>Se ocultaron {diffBody.masked} valores sensibles en este diff.</div>
              )}
              <div className={styles.diffBox}>{diffBody.diff || "(sin diferencias)"}</div>
            </>
          ) : (
            <div className={styles.emptyState}>{diffBody?.reason ?? "Sin datos."}</div>
          )}
        </>
      )}
    </div>
  );
}

// ── Panel Historial (F5b) — degrada ante 404 feature_disabled (D6) ──────────
function HistoryPanel({ onOpenExecution }: { onOpenExecution: (id: number) => void }) {
  const historyQ = useQuery({
    queryKey: ["console-history"],
    queryFn: () => Console.historyRaw(20),
  });

  if (historyQ.isLoading) return <div className={styles.emptyState}>Cargando…</div>;

  // rawGet enruta el body de un 4xx/5xx a `errorBody`, no a `data` (client.ts):
  // el 404 feature_disabled de D6 llega por ahí, nunca por `data`.
  const state = historyPanelState({
    status: historyQ.data?.status ?? 0,
    body: historyQ.data?.ok ? historyQ.data?.data : historyQ.data?.errorBody,
  });
  if (!state.available) {
    return <div className={styles.emptyState}>{state.reason}</div>;
  }
  const items = state.items as Array<{ id: number; agent_type?: string; status?: string; started_at?: string }>;
  if (items.length === 0) return <div className={styles.emptyState}>Sin sesiones anteriores.</div>;

  return (
    <div>
      {items.map((item) => (
        <button key={item.id} type="button" className={styles.historyRow} onClick={() => onOpenExecution(item.id)}>
          <span>#{item.id} · {item.agent_type ?? "?"} · {item.status ?? "?"}</span>
          <span className={styles.contextLabel}>{item.started_at ?? ""}</span>
        </button>
      ))}
    </div>
  );
}

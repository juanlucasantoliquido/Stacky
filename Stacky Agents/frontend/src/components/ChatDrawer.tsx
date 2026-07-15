/**
 * ChatDrawer – drawer deslizante para ejecuciones de agentes y chat libre.
 *
 * Fase 1 (setup): Selector de agente + modelo + ticket + botón Lanzar.
 * Fase 2 (chat):  Burbuja de prompt, streaming de respuesta, preguntas
 *                 interactivas y mensajes de seguimiento libres.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";

import ReactMarkdown from "react-markdown";

const DOC_AGENT = "DocConsultor.agent.md";

import { useQuery } from "@tanstack/react-query";

import { AgentRoles, Agents, Chat, DocsRag, Projects, Tickets } from "../api/endpoints";
import type { ChatTurnMessage, ChatToolLog, DocsRagSource } from "../api/endpoints";
import type { Ticket } from "../types";
import { useWorkbench } from "../store/workbench";
import LoadErrorState from "./LoadErrorState";
import { formatLoadErrorMessage } from "../utils/loadError";
import styles from "./ChatDrawer.module.css";

// ── Types ────────────────────────────────────────────────────────────────────

type BubbleKind = "user" | "assistant" | "system" | "toolLog" | "question";

interface Bubble {
  id: string;
  kind: BubbleKind;
  text: string;
  streaming?: boolean;
  toolLog?: ChatToolLog[];
  sources?: DocsRagSource[];
}

// ── Helper ───────────────────────────────────────────────────────────────────

let _bubbleCounter = 0;
function nextId() { return `b${++_bubbleCounter}`; }

// ── ChatDrawer ───────────────────────────────────────────────────────────────

export default function ChatDrawer() {
  const {
    chatDrawerOpen,
    chatDrawerModel,
    chatDrawerTicketId,
    setChatDrawerOpen,
    activeProject,
    // WS1 usa agentRuntime; lo exponemos como "runtime" para compatibilidad WS2
    agentRuntime: runtime,
  } = useWorkbench();

  // ── Proyecto anterior para detectar cambio ────────────────────────────────
  const prevProjectRef = useRef<string | undefined>(undefined);

  // ── Setup state ────────────────────────────────────────────────────────────
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [ticketQuery, setTicketQuery] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filteredTickets, setFilteredTickets] = useState<Ticket[]>([]);
  const [ticketsLoadError, setTicketsLoadError] = useState<string | null>(null);
  const [ticketsReloadKey, setTicketsReloadKey] = useState(0);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);

  // ── Workspace root for tool_executor file writes ─────────────────────────
  const [workspaceDir, setWorkspaceDir] = useState<string | null>(null);

  // ── Chat state ─────────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<"setup" | "chat">("setup");
  const [firstTurnDone, setFirstTurnDone] = useState(false);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [history, setHistory] = useState<ChatTurnMessage[]>([]);
  const [userInput, setUserInput] = useState("");
  const [sending, setSending] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [indexing, setIndexing] = useState(false);
  const [indexMsg, setIndexMsg] = useState<string | null>(null);
  const [exportFeedback, setExportFeedback] = useState(false);

  const chatBottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: agentsData } = useQuery({
    queryKey: ["vsCodeAgents"],
    queryFn: Agents.vsCodeAgents,
    staleTime: 60_000,
  });

  const { data: modelsData } = useQuery({
    queryKey: ["models"],
    queryFn: () => Agents.models(),
    staleTime: 60_000,
  });

  const agentsList = agentsData ?? [];
  const modelsList = modelsData?.models ?? [];

  // ── Agent roles (utilitario = visible en chat drawer) ─────────────────────
  const { data: rolesData } = useQuery({
    queryKey: ["agentRoles"],
    queryFn: AgentRoles.list,
    staleTime: 60_000,
  });

  const toolAgents = Object.entries(rolesData?.roles ?? {})
    .filter(([, r]) => r.utilitario)
    .map(([filename, r]) => ({ filename, label: r.name || filename, description: r.description }));

  // Inicializar selectedAgent al primer agente utilitario cuando cargan
  useEffect(() => {
    if (toolAgents.length > 0 && !selectedAgent) {
      const preferred = toolAgents.find((a) => a.filename === DOC_AGENT);
      setSelectedAgent(preferred?.filename ?? toolAgents[0].filename);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolAgents.length]);

  // ── Reset chat cuando cambia el proyecto ────────────────────────────────────
  useEffect(() => {
    const current = activeProject?.name;
    if (prevProjectRef.current !== undefined && prevProjectRef.current !== current) {
      setPhase("setup");
      setBubbles([]);
      setHistory([]);
      setFirstTurnDone(false);
      setChatError(null);
      setLaunchError(null);
      setSelectedTicket(null);
      setIndexMsg(null);
    }
    prevProjectRef.current = current;
  }, [activeProject?.name]);

  // ── Reset chat cuando cambia el agente ───────────────────────────────────
  const prevAgentRef = useRef<string>("");
  useEffect(() => {
    if (prevAgentRef.current !== selectedAgent) {
      setPhase("setup");
      setBubbles([]);
      setHistory([]);
      setFirstTurnDone(false);
      setChatError(null);
      setLaunchError(null);
      setIndexMsg(null);
    }
    prevAgentRef.current = selectedAgent;
  }, [selectedAgent]);

  // ── Al abrir el drawer: obtener workspace_root (sin resetear chat activo) ───
  useEffect(() => {
    if (!chatDrawerOpen) return;
    if (chatDrawerModel) setSelectedModel(chatDrawerModel);
    Projects.agentBootstrap()
      .then((r) => { if (r.workspace_root) setWorkspaceDir(r.workspace_root); })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatDrawerOpen]);

  // ── Load tickets when agent / project changes ──────────────────────────────
  useEffect(() => {
    if (!chatDrawerOpen || !selectedAgent) return;
    setTicketsLoadError(null);
    // WS1: Tickets.list solo acepta project (sin agent_filename)
    Tickets.list(activeProject?.name ?? undefined)
      .then((t) => {
        setTickets(t);
        setFilteredTickets(t.slice(0, 20));
        // Auto-select ticket pre-seleccionado desde AgentLaunchModal
        if (chatDrawerTicketId) {
          const match = t.find((ticket) => ticket.id === chatDrawerTicketId);
          if (match) setSelectedTicket(match);
        }
      })
      .catch((e) => setTicketsLoadError(formatLoadErrorMessage(e)));
  }, [chatDrawerOpen, selectedAgent, activeProject?.name, ticketsReloadKey]);

  // ── Ticket filter ──────────────────────────────────────────────────────────
  useEffect(() => {
    const q = ticketQuery.toLowerCase().trim();
    if (!q) { setFilteredTickets(tickets.slice(0, 20)); return; }
    setFilteredTickets(
      tickets
        .filter((t) => t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q))
        .slice(0, 20)
    );
  }, [ticketQuery, tickets]);

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  // ── Indexar documentación (solo modo DocConsultor) ─────────────────────
  const isDocMode = selectedAgent === "DocConsultor.agent.md";

  async function handleIndexDocs() {
    setIndexing(true);
    setIndexMsg(null);
    try {
      const res = await DocsRag.index({ project_name: activeProject?.name });
      if (res.ok) {
        setIndexMsg(`✓ ${res.chunks_indexed} fragmentos indexados de ${res.files_scanned} ficheros.${res.warning ? " ⚠ " + res.warning : ""}`);
      } else {
        setIndexMsg(`✗ Error: ${res.error ?? "desconocido"}`);
      }
    } catch (err: unknown) {
      setIndexMsg(`✗ ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIndexing(false);
    }
  }

  // ── Launch first turn via Chat.turn() ────────────────────────────────────
  async function handleLaunch() {
    if (!selectedAgent) return;
    setLaunchError(null);

    // Modo DocConsultor o sin ticket: saltar directamente al chat libre
    if (isDocMode || !selectedTicket) {
      setHistory([]);
      setBubbles([]);
      setPhase("chat");
      setFirstTurnDone(true);
      setTimeout(() => textareaRef.current?.focus(), 50);
      return;
    }

    setLaunching(true);
    setFirstTurnDone(false);

    const userCtx = `Ticket #${selectedTicket.ado_id}: ${selectedTicket.title}`
      + (selectedTicket.description ? `\n\n${selectedTicket.description}` : "");

    const userBubble: Bubble = {
      id: nextId(),
      kind: "user",
      text: `#${selectedTicket.ado_id}: ${selectedTicket.title}`,
    };
    const waitingBubble: Bubble = { id: nextId(), kind: "assistant", text: "", streaming: true };

    const initMessages: ChatTurnMessage[] = [{ role: "user", content: userCtx }];
    setHistory(initMessages);
    setBubbles([userBubble, waitingBubble]);
    setPhase("chat");

    try {
      const res = await Chat.turn({
        agent_filename: selectedAgent,
        model: selectedModel || null,
        messages: initMessages,
        workspace_dir: workspaceDir,
        runtime,
        project_name: activeProject?.name ?? null,
      });

      const assistantText = res.text ?? "";
      const finalHistory: ChatTurnMessage[] = [
        ...initMessages,
        { role: "assistant", content: assistantText },
      ];
      setHistory(finalHistory);
      setBubbles([userBubble, { ...waitingBubble, text: assistantText, streaming: false, toolLog: res.tool_log }]);
      setFirstTurnDone(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setLaunchError(msg);
      setPhase("setup");
      setBubbles([]);
      setHistory([]);
    } finally {
      setLaunching(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }

  // ── Send free-turn message ─────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const text = userInput.trim();
    if (!text || sending || !selectedAgent) return;
    setSending(true);
    setChatError(null);

    const userBubble: Bubble = { id: nextId(), kind: "user", text };
    const streamingBubble: Bubble = { id: nextId(), kind: "assistant", text: "", streaming: true };

    setBubbles((prev) => [...prev, userBubble, streamingBubble]);
    setUserInput("");

    const updatedHistory: ChatTurnMessage[] = [
      ...history,
      { role: "user", content: text },
    ];
    setHistory(updatedHistory);

    try {
      let assistantText = "";
      let toolLog: ChatToolLog[] | undefined;
      let ragSources: DocsRagSource[] | undefined;

      if (isDocMode) {
        const res = await DocsRag.chat({
          messages: updatedHistory,
          agent_filename: selectedAgent,
          model: selectedModel || null,
          workspace_dir: workspaceDir,
        });
        assistantText = res.text ?? "";
        ragSources = res.sources?.length ? res.sources : undefined;
      } else {
        const res = await Chat.turn({
          agent_filename: selectedAgent,
          model: selectedModel || null,
          messages: updatedHistory,
          workspace_dir: workspaceDir,
          runtime,
          project_name: activeProject?.name ?? null,
        });
        assistantText = res.text ?? "";
        toolLog = res.tool_log;
      }

      const finalHistory: ChatTurnMessage[] = [
        ...updatedHistory,
        { role: "assistant", content: assistantText },
      ];
      setHistory(finalHistory);

      setBubbles((prev) =>
        prev.map((b) =>
          b.id === streamingBubble.id
            ? { ...b, text: assistantText, streaming: false, toolLog, sources: ragSources }
            : b
        )
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setChatError(msg);
      setBubbles((prev) => prev.filter((b) => b.id !== streamingBubble.id));
    } finally {
      setSending(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [userInput, sending, selectedAgent, selectedModel, history]);

  // textarea Enter to send (Shift+Enter = newline)
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // Copy text to clipboard
  async function copyText(text: string) {
    try { await navigator.clipboard.writeText(text); } catch { /* noop */ }
  }

  // Reset back to setup
  function resetToSetup() {
    setPhase("setup");
    setFirstTurnDone(false);
    setBubbles([]);
    setHistory([]);
    setChatError(null);
    setSelectedTicket(null);
    setTicketQuery("");
  }

  // ── Export chat ────────────────────────────────────────────────────────────
  function handleExportChat() {
    const projectName = activeProject?.name ?? "Proyecto";
    const dateStr = new Date().toLocaleString("es-ES", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

    const lines: string[] = [
      `# Chat DocConsultor — ${projectName}`,
      `*${dateStr}*`,
      ``,
    ];

    for (const b of bubbles) {
      if (b.kind === "user") {
        lines.push(`---`, ``);
        lines.push(`**Yo:** ${b.text}`, ``);
      } else if (b.kind === "assistant" && b.text) {
        lines.push(`**DocConsultor:**`, ``);
        lines.push(b.text, ``);

      }
    }

    const text = lines.join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setExportFeedback(true);
      setTimeout(() => setExportFeedback(false), 2000);
    }).catch(() => {});
  }

  // ── Close ──────────────────────────────────────────────────────────────────
  function handleClose() {
    setChatDrawerOpen(false);
  }

  const canSendFreeMessage = phase === "chat" && firstTurnDone && !sending;

  const currentAgentMeta = toolAgents.find((a) => a.filename === selectedAgent) ?? toolAgents[0];

  const currentAgentName =
    agentsList.find((a) => a.filename === selectedAgent)?.name ??
    currentAgentMeta?.label ?? selectedAgent;

  return (
    <>
      {/* Backdrop — solo visible cuando el drawer está abierto, sin cerrar al hacer clic */}
      {chatDrawerOpen && <div className={styles.overlay} aria-hidden="true" />}

      {/* Drawer — siempre montado para preservar el estado del chat */}
      <aside
        className={`${styles.drawer}${!chatDrawerOpen ? " " + styles.drawerClosed : ""}`}
        role="complementary"
        aria-label="Chat documental"
      >

        {/* Header */}
        <div className={styles.header}>
          <span className={styles.headerTitle}>
            {phase === "setup" ? "💬 Nuevo Chat" : `🤖 ${currentAgentName}`}
          </span>
          {phase === "chat" && (
            <>
              <button
                className={styles.closeBtn}
                onClick={handleExportChat}
                title="Exportar chat (copiar al portapapeles)"
                style={exportFeedback ? { color: "#86efac" } : undefined}
              >
                {exportFeedback ? "✓ Copiado" : "⬆ Exportar"}
              </button>
              <button className={styles.closeBtn} onClick={resetToSetup} title="Nueva conversación">
                ✦
              </button>
            </>
          )}
          <button className={styles.closeBtn} onClick={handleClose} title="Cerrar" aria-label="Cerrar chat">
            ✕
          </button>
        </div>

        {/* ── SETUP PHASE ─────────────────────────────────────────────────── */}
        {phase === "setup" && (
          <div className={styles.setup}>
            {/* Selector de agente */}
            <div className={styles.field}>
              <span className={styles.label}>Agente</span>
              <select
                className={styles.select}
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
              >
                {toolAgents.map((ag) => (
                  <option key={ag.filename} value={ag.filename} title={ag.description}>
                    {ag.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Model */}
            <div className={styles.field}>
              <span className={styles.label}>Modelo</span>
              {modelsList.length > 0 ? (
                <select
                  className={styles.select}
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  <option value="">— Default —</option>
                  {modelsList.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  className={styles.input}
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  placeholder="ej: gpt-4o (dejar vacío = default)"
                />
              )}
            </div>

            {/* Docs RAG: indexar documentación */}
            {isDocMode && (
              <div className={styles.field}>
                <span className={styles.label}>Documentación</span>
                <button
                  className={styles.indexBtn}
                  disabled={indexing}
                  onClick={handleIndexDocs}
                >
                  {indexing ? <span className={styles.spinner} /> : "⟳ Indexar docs"}
                </button>
                {indexMsg && (
                  <div className={indexMsg.startsWith("✓") ? styles.indexMsgOk : styles.errorNotice}>
                    {indexMsg}
                  </div>
                )}
              </div>
            )}

            {/* Ticket search */}
            {selectedAgent && !isDocMode && (
              <div className={styles.field}>
                <span className={styles.label}>Ticket</span>
                <input
                  className={styles.input}
                  value={ticketQuery}
                  onChange={(e) => setTicketQuery(e.target.value)}
                  placeholder="Buscar por título o ID…"
                />
                {ticketsLoadError && (
                  <LoadErrorState
                    compact
                    what="los tickets"
                    error={ticketsLoadError}
                    onRetry={() => setTicketsReloadKey((k) => k + 1)}
                  />
                )}
                {filteredTickets.length > 0 && (
                  <div className={styles.ticketList}>
                    {filteredTickets.map((t) => (
                      <div
                        key={t.id}
                        className={`${styles.ticketItem} ${selectedTicket?.id === t.id ? styles.selected : ""}`}
                        onClick={() => setSelectedTicket(t)}
                      >
                        <strong>#{t.ado_id}</strong> {t.title}
                      </div>
                    ))}
                  </div>
                )}
                {selectedTicket && (
                  <div style={{ fontSize: "0.75rem", color: "#a78bfa", marginTop: "0.25rem" }}>
                    ✓ #{selectedTicket.ado_id} {selectedTicket.title}
                  </div>
                )}
              </div>
            )}

            {launchError && (
              <div className={styles.errorNotice}>{launchError}</div>
            )}

            <button
              className={styles.launchBtn}
              disabled={!selectedAgent || launching}
              onClick={handleLaunch}
            >
              {launching ? <span className={styles.spinner} /> : "▶ Lanzar"}
            </button>
          </div>
        )}

        {/* ── CHAT PHASE ──────────────────────────────────────────────────── */}
        {phase === "chat" && (
          <>
            <div className={styles.chatArea}>
              {bubbles.map((b) => (
                <BubbleView
                  key={b.id}
                  bubble={b}
                  onCopy={copyText}
                  // Pass question answer props only for active question
                  isActiveQuestion={false}
                  pendingAnswer={""}
                  onAnswerChange={() => {}}
                  onAnswerSubmit={() => {}}
                />
              ))}

              {/* Streaming indicator while first turn loads */}
              {launching && phase === "chat" && (
                <div className={`${styles.bubble} ${styles.system}`}>
                  Generando respuesta<span className={styles.streamingDot} />
                </div>
              )}

              {chatError && (
                <div className={styles.errorNotice}>{chatError}</div>
              )}

              <div ref={chatBottomRef} />
            </div>

            {/* Footer input */}
            <div className={styles.footer}>
              <div className={styles.inputRow}>
                <textarea
                  ref={textareaRef}
                  className={styles.messageInput}
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={canSendFreeMessage ? "Continuá la conversación…" : launching ? "Esperando respuesta…" : "Lanzá una ejecución primero…"}
                  disabled={!canSendFreeMessage}
                  rows={1}
                />
                <button
                  className={styles.sendBtn}
                  disabled={!canSendFreeMessage || !userInput.trim()}
                  onClick={sendMessage}
                  title="Enviar (Enter)"
                >
                  {sending ? <span className={styles.spinner} /> : "↑"}
                </button>
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}

// ── BubbleView ────────────────────────────────────────────────────────────────

interface BubbleViewProps {
  bubble: Bubble;
  onCopy: (text: string) => void;
  isActiveQuestion: boolean;
  pendingAnswer: string;
  onAnswerChange: (v: string) => void;
  onAnswerSubmit: () => void;
}

function BubbleView({
  bubble,
  onCopy,
  isActiveQuestion,
  pendingAnswer,
  onAnswerChange,
  onAnswerSubmit,
}: BubbleViewProps) {
  const cls = `${styles.bubble} ${styles[bubble.kind]}`;

  if (bubble.kind === "question") {
    return (
      <div className={cls}>
        <div>❓ {bubble.text}</div>
        {isActiveQuestion && (
          <div className={styles.questionForm}>
            <input
              className={styles.questionInput}
              value={pendingAnswer}
              onChange={(e) => onAnswerChange(e.target.value)}
              placeholder="Tu respuesta…"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); onAnswerSubmit(); } }}
              autoFocus
            />
            <button className={styles.answerBtn} onClick={onAnswerSubmit} disabled={!pendingAnswer.trim()}>
              Enviar
            </button>
          </div>
        )}
      </div>
    );
  }

  if (bubble.kind === "assistant") {
    return (
      <div className={cls}>
        <button
          className={styles.copyBtn}
          onClick={() => onCopy(bubble.text)}
          title="Copiar respuesta"
        >
          ⎘ copiar
        </button>
        <div className={styles.prose}>
          <ReactMarkdown>{bubble.text}</ReactMarkdown>
        </div>
        {bubble.streaming && <span className={styles.streamingDot} />}
        {bubble.toolLog && bubble.toolLog.length > 0 && (
          <div className={`${styles.bubble} ${styles.toolLog}`} style={{ marginTop: "0.5rem" }}>
            {bubble.toolLog.map((t, i) => (
              <div key={i}>
                <strong>{t.tool}</strong>{t.ok ? " ✓" : " ✗"}{" "}
                <span style={{ opacity: 0.7 }}>{t.args}</span>
              </div>
            ))}
          </div>
        )}

      </div>
    );
  }

  if (bubble.kind === "system") {
    return <div className={cls}>{bubble.text}</div>;
  }

  // user / toolLog
  return (
    <div className={cls}>
      {bubble.kind === "toolLog"
        ? <pre style={{ margin: 0 }}>{bubble.text}</pre>
        : bubble.text}
    </div>
  );
}

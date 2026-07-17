import React, { useState, useEffect, useRef } from "react";
import type { VsCodeAgent, Ticket } from "../types";
import { Projects, Tickets, ClaudeCli, type ClaudeSessionStatus } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import {
  humanizeAgentLaunchError,
  launchAgentWithRuntime,
  launchInProgressLabel,
  openConsoleIfCliRuntime,
  parseBusinessPreflightError,
  runtimeDisplayLabel,
} from "../services/agentLaunch";
import AgentRuntimeSelector from "./AgentRuntimeSelector";
import ClaudeCliConfigModal from "./ClaudeCliConfigModal";
import PixelAvatar from "./PixelAvatar";
import LoadErrorState from "./LoadErrorState";
import { formatLoadErrorMessage } from "../utils/loadError";
import { shouldCloseOnBackdrop } from "../services/uiGuards";
import styles from "./AgentLaunchModal.module.css";

interface TicketComment { author: string; date: string; text: string; }

type BridgeStatus = "unknown" | "checking" | "ready" | "down";

interface BridgeError {
  // Categoría del error para que el usuario sepa qué hacer
  kind: "extension_down" | "bridge_timeout" | "bridge_error" | "ticket_not_found" | "unknown";
  // Mensaje listo para mostrar
  message: string;
  // Detalle técnico (HTTP status + body) para el banner expandible
  detail?: string;
}

interface AgentLaunchModalProps {
  agent: VsCodeAgent;
  avatarValue: string | null;
  onClose: () => void;
}

/**
 * Health-check del bridge de la extensión VS Code.
 *
 * Consulta el estado del bridge del proyecto activo vía backend.
 * Devuelve `true` solo si el bridge responde healthy — diferenciamos esto
 * explícitamente del flujo de POST /open-chat para evitar falsos positivos
 * del banner "extensión no está activa" cuando el problema real es otro
 * (CORS, timeout puntual, payload mal armado, ticket inexistente, etc.).
 *
 * No expone errores: cualquier fallo → false.
 */
async function checkBridgeHealth(projectName: string | null): Promise<boolean> {
  if (!projectName) return false;
  try {
    const status = await Projects.vscodeStatus(projectName);
    return status.ready === true;
  } catch {
    return false;
  }
}

export default function AgentLaunchModal({ agent, avatarValue, onClose }: AgentLaunchModalProps) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const [query, setQuery] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filtered, setFiltered] = useState<Ticket[]>([]);
  const [ticketsLoadError, setTicketsLoadError] = useState<string | null>(null);
  const [ticketsReloadKey, setTicketsReloadKey] = useState(0);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [comments, setComments] = useState<TicketComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>("unknown");
  const [error, setError] = useState<BridgeError | null>(null);
  const [success, setSuccess] = useState(false);
  // Estado de configuración de Claude Code CLI (binario + sesión).
  const [claudeSession, setClaudeSession] = useState<ClaudeSessionStatus | null>(null);
  const [claudeChecking, setClaudeChecking] = useState(false);
  const [showClaudeConfig, setShowClaudeConfig] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const claudeReady = claudeSession?.logged_in === true;
  const claudeNeedsConfig = agentRuntime === "claude_code_cli" && !claudeReady;

  // Sondea el estado de Claude Code (binario + sesión). Devuelve si quedó listo.
  async function probeClaude(): Promise<boolean> {
    setClaudeChecking(true);
    try {
      const s = await ClaudeCli.session();
      setClaudeSession(s);
      return s.logged_in === true;
    } catch {
      setClaudeSession(null);
      return false;
    } finally {
      setClaudeChecking(false);
    }
  }

  // Al elegir un runtime; si es Claude Code y no está configurado, abre el modal.
  async function handleRuntimeChange(rt: typeof agentRuntime) {
    setAgentRuntime(rt);
    setError(null);
    if (rt === "claude_code_cli") {
      const ready = claudeSession ? claudeReady : await probeClaude();
      if (!ready) setShowClaudeConfig(true);
    }
  }

  // load tickets once + initial bridge health probe (informativo, no bloqueante)
  useEffect(() => {
    setTicketsLoadError(null);
    Tickets.list(activeProjectName).then((t) => {
      setTickets(t);
      setFiltered(t.slice(0, 20));
    }).catch((e) => setTicketsLoadError(formatLoadErrorMessage(e)));
    searchRef.current?.focus();

    // Probe inicial del bridge — si está caído, mostramos un aviso suave
    // que NO bloquea seleccionar ticket ni escribir mensaje. El usuario puede
    // levantar VS Code mientras prepara la asignación.
    setBridgeStatus("checking");
    checkBridgeHealth(activeProjectName).then((ok) => {
      setBridgeStatus(ok ? "ready" : "down");
    });

    // Si el runtime persistido ya es Claude Code, sondear su estado al abrir
    // para mostrar el badge/banner de configuración sin esperar al clic.
    if (agentRuntime === "claude_code_cli") {
      void probeClaude();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProjectName, ticketsReloadKey]);

  // debounced filter
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (!query.trim()) {
        setFiltered(tickets.slice(0, 20));
      } else {
        const q = query.toLowerCase();
        setFiltered(
          tickets
            .filter(
              (t) =>
                String(t.ado_id).includes(q) ||
                t.title.toLowerCase().includes(q) ||
                (t.project ?? "").toLowerCase().includes(q)
            )
            .slice(0, 20)
        );
      }
    }, 200);
  }, [query, tickets]);

  // fetch comments when a ticket is selected
  useEffect(() => {
    if (!selected) { setComments([]); return; }
    setCommentsLoading(true);
    Tickets.comments(selected.id)
      .then((r) => setComments(r.comments ?? []))
      .catch(() => setComments([]))
      .finally(() => setCommentsLoading(false));
  }, [selected]);

  /**
   * Re-chequea el bridge cuando el usuario hace clic en "Reintentar" del banner.
   * Cubre el caso típico: usuario levanta VS Code después de abrir el modal.
   */
  async function retryBridgeProbe() {
    setBridgeStatus("checking");
    const ok = await checkBridgeHealth(activeProjectName);
    setBridgeStatus(ok ? "ready" : "down");
    if (ok) setError(null);
  }

  /**
   * Convierte un error del backend `/api/agents/open-chat` en un `BridgeError`
   * con un mensaje específico para el usuario. El backend devuelve HTTP
   * granulares: 503 (bridge caído), 504 (timeout), 502 (bridge respondió 5xx),
   * 400 (payload inválido), 404 (ticket no existe).
   */
  function mapBackendError(rawMessage: string): BridgeError {
    const m = rawMessage || "";
    if (m.includes("503")) {
      return {
        kind: "extension_down",
        message: "La extensión VS Code no está activa. Abrí VS Code con la extensión Stacky y reintentá.",
        detail: m,
      };
    }
    if (m.includes("504")) {
      return {
        kind: "bridge_timeout",
        message: "VS Code recibió la solicitud pero tardó demasiado en responder. Reintentá en unos segundos.",
        detail: m,
      };
    }
    if (m.includes("502")) {
      return {
        kind: "bridge_error",
        message: "VS Code respondió con un error al abrir el chat. Revisá los logs de la extensión Stacky.",
        detail: m,
      };
    }
    if (m.includes("404")) {
      return {
        kind: "ticket_not_found",
        message: "El ticket seleccionado no se encontró en la base de Stacky. Probá sincronizar tickets primero.",
        detail: m,
      };
    }
    return {
      kind: "unknown",
      message: "No se pudo abrir el chat. Revisá la consola del backend para más detalle.",
      detail: m,
    };
  }

  async function handleLaunch() {
    if (!selected) return;
    setLoading(true);
    setError(null);

    try {
      const contextBlocks = message.trim()
        ? [
            {
              id: "modal_user_input",
              kind: "editable" as const,
              title: "Mensaje adicional",
              content: message.trim(),
              source: { type: "modal_user_input" },
            },
          ]
        : [];

      const result = await launchAgentWithRuntime({
        ticketId: selected.id,
        projectName: activeProjectName,
        runtime: agentRuntime,
        contextBlocks,
        vscodeAgent: agent,
      });
      setSuccess(true);
      if (agentRuntime === "github_copilot") {
        setBridgeStatus("ready");
      } else {
        // Runtimes CLI (Codex / Claude): abrir la consola in-page para ver la
        // actividad en vivo y poder responderle al agente.
        openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      }
      setTimeout(onClose, 1200);
    } catch (e) {
      // Plan 133 F2 — el preflight de negocio server-side puede rechazar el
      // lanzamiento con un 400 accionable; si vino ese shape, mostrarlo tal
      // cual (ya es un mensaje pensado para el operador) en vez del genérico.
      const businessPreflightMessage = parseBusinessPreflightError(e);
      if (businessPreflightMessage) {
        setError({ kind: "unknown", message: businessPreflightMessage, detail: String(e) });
      } else if (agentRuntime === "github_copilot") {
        setError(mapBackendError(String(e)));
      } else {
        setError({
          kind: "unknown",
          message: humanizeAgentLaunchError(e),
          detail: String(e),
        });
      }
      if (agentRuntime === "github_copilot" && String(e).includes("503")) {
        setBridgeStatus("down");
      }
    } finally {
      setLoading(false);
    }
  }

  // close on backdrop click
  function handleBackdrop(e: React.MouseEvent) {
    if (e.target !== e.currentTarget) return;
    const dirty = selected != null || message.trim().length > 0;
    if (shouldCloseOnBackdrop({ dirty, busy: loading })) onClose();
  }

  const displayName = agent.name ?? agent.filename.replace(/\.agent\.md$/i, "");

  return (
    <div className={styles.backdrop} onClick={handleBackdrop}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Asignar ticket">
        {/* Header */}
        <div className={styles.header}>
          <PixelAvatar value={avatarValue} size="sm" name={displayName} />
          <div className={styles.headerText}>
            <span className={styles.agentName}>{displayName}</span>
            <span className={styles.subtitle}>¿Qué ticket querés trabajar?</span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
        </div>

        <div className={styles.runtimeSection}>
          <AgentRuntimeSelector
            value={agentRuntime}
            onChange={handleRuntimeChange}
            disabled={loading || success}
            claudeNeedsConfig={claudeNeedsConfig}
          />
          {/* Plan 36 — F3: etiqueta de runtime efectivo */}
          <p className={styles.effectiveRuntime} role="status">
            Lanzará con: <strong>{runtimeDisplayLabel(agentRuntime)}</strong>
            {agentRuntime === "github_copilot"
              ? " — abre VS Code Chat (no la consola headless de Stacky)."
              : " — abre la consola headless de Stacky."}
          </p>
        </div>

        {/* Aviso de configuración de Claude Code (no bloquea seleccionar ticket) */}
        {agentRuntime === "claude_code_cli" && !claudeReady && !claudeChecking && (
          <div className={styles.warning} role="status">
            <span>
              Claude Code no está configurado
              {claudeSession?.error ? ` (${claudeSession.error})` : " (falta iniciar sesión o instalar el CLI)"}.
              {" "}Stacky no cambia a GitHub Copilot por vos; configurá este runtime o elegí GitHub Copilot manualmente.
            </span>
            <button
              className={styles.retryBtn}
              onClick={() => setShowClaudeConfig(true)}
              type="button"
            >
              ⚙ Configurar
            </button>
          </div>
        )}
        {agentRuntime === "claude_code_cli" && claudeChecking && (
          <div className={styles.warning} role="status">
            <span>Verificando Claude Code…</span>
          </div>
        )}

        {/* Aviso suave si el bridge está caído (no bloquea selección) */}
        {agentRuntime === "github_copilot" && bridgeStatus === "down" && !error && (
          <div className={styles.warning} role="status">
            <span>
              VS Code no está conectado al bridge de Stacky. Podés seleccionar el ticket; cuando abras VS Code reintentá.
            </span>
            <button className={styles.retryBtn} onClick={retryBridgeProbe} type="button">
              Reintentar
            </button>
          </div>
        )}

        {/* Search */}
        <div className={styles.searchWrap}>
          <input
            ref={searchRef}
            className={styles.search}
            type="text"
            placeholder="Buscar por ID, título o proyecto…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* Ticket list */}
        <div className={styles.list}>
          {ticketsLoadError ? (
            <LoadErrorState
              compact
              what="los tickets"
              error={ticketsLoadError}
              onRetry={() => setTicketsReloadKey((k) => k + 1)}
            />
          ) : filtered.length === 0 ? (
            <div className={styles.empty}>No se encontraron tickets</div>
          ) : (
            filtered.map((t) => (
              <button
                key={t.id}
                className={selected?.id === t.id ? styles.ticketActive : styles.ticket}
                onClick={() => setSelected(t)}
              >
                <span className={styles.ticketId}>ADO-{t.ado_id}</span>
                <span className={styles.ticketTitle}>{t.title}</span>
                {t.ado_state && (
                  <span className={styles.ticketState}>{t.ado_state}</span>
                )}
              </button>
            ))
          )}
        </div>

        {/* Optional message */}
        <textarea
          className={styles.messageInput}
          placeholder="Mensaje inicial (opcional)…"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={2}
        />

        {/* Error específico (post-launch) */}
        {error && (
          <div className={styles.error} role="alert">
            <span>⚠️ {error.message}</span>
            {error.kind === "extension_down" && (
              <button className={styles.retryBtn} onClick={retryBridgeProbe} type="button">
                Reintentar conexión
              </button>
            )}
            {error.detail && (
              <details className={styles.errorDetail}>
                <summary>Detalle técnico</summary>
                <pre>{error.detail}</pre>
              </details>
            )}
          </div>
        )}

        {/* Actions */}
        <div className={styles.actions}>
          <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
          <button
            className={styles.launchBtn}
            onClick={handleLaunch}
            disabled={!selected || loading || success || (agentRuntime === "claude_code_cli" && !claudeReady)}
            title={
              agentRuntime === "claude_code_cli" && !claudeReady
                ? "Stacky no cambia a GitHub Copilot por vos; configurá este runtime o elegí GitHub Copilot manualmente."
                : undefined
            }
          >
            {success
              ? "✓ Iniciado"
              : loading
              ? launchInProgressLabel(agentRuntime)
              : agentRuntime === "github_copilot"
              ? "OK — Abrir en GitHub Copilot"
              : "▶ Lanzar ejecución"}
          </button>
        </div>
      </div>

      {showClaudeConfig && (
        <ClaudeCliConfigModal
          onClose={() => setShowClaudeConfig(false)}
          onConfigured={() => {
            void probeClaude();
          }}
        />
      )}
    </div>
  );
}

import React, { useState, useEffect, useRef } from "react";
import type { VsCodeAgent, Ticket } from "../types";
import { Agents, Tickets } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentLaunchModal.module.css";

interface TicketComment { author: string; date: string; text: string; }

// Endpoint del bridge de la extensión VS Code (Stacky Agents).
// Solo lo usamos para el health-check informativo: la llamada real a /open-chat
// va por el backend Flask vía `Agents.openChat()`.
const BRIDGE_BASE = "http://localhost:5052";

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
 * Pega a `GET http://localhost:5052/health` (CORS abierto en la extensión).
 * Devuelve `true` solo si el bridge responde 200 — diferenciamos esto
 * explícitamente del flujo de POST /open-chat para evitar falsos positivos
 * del banner "extensión no está activa" cuando el problema real es otro
 * (CORS, timeout puntual, payload mal armado, ticket inexistente, etc.).
 *
 * Timeout corto (1.5s) — si no responde rápido, asumimos que está caído.
 * No expone errores: cualquier fallo → false.
 */
async function checkBridgeHealth(): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch(`${BRIDGE_BASE}/health`, {
      method: "GET",
      signal: ctrl.signal,
    });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

export default function AgentLaunchModal({ agent, avatarValue, onClose }: AgentLaunchModalProps) {
  const [query, setQuery] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filtered, setFiltered] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [comments, setComments] = useState<TicketComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>("unknown");
  const [error, setError] = useState<BridgeError | null>(null);
  const [success, setSuccess] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // load tickets once + initial bridge health probe (informativo, no bloqueante)
  useEffect(() => {
    Tickets.list().then((t) => {
      setTickets(t);
      setFiltered(t.slice(0, 20));
    }).catch(() => {});
    searchRef.current?.focus();

    // Probe inicial del bridge — si está caído, mostramos un aviso suave
    // que NO bloquea seleccionar ticket ni escribir mensaje. El usuario puede
    // levantar VS Code mientras prepara la asignación.
    setBridgeStatus("checking");
    checkBridgeHealth().then((ok) => {
      setBridgeStatus(ok ? "ready" : "down");
    });
  }, []);

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
    const ok = await checkBridgeHealth();
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
      // Routing correcto: vamos al backend Flask, NO directo al bridge.
      // El backend (`/api/agents/open-chat`) ya:
      //   1. Levanta el ticket de la DB con todos los metadatos
      //   2. Enriquece con comentarios + adjuntos de ADO
      //   3. Llama al bridge desde el server (sin CORS browser)
      //   4. Devuelve errores HTTP granulares (503/504/502)
      // El message adicional opcional se manda como un context_block libre
      // siguiendo el shape de `ContextBlock` (ver `frontend/src/types.ts`).
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

      await Agents.openChat({
        ticket_id: selected.id,
        context_blocks: contextBlocks,
        vscode_agent_filename: agent.filename,
      });
      setSuccess(true);
      // Bridge respondió OK → confirmamos status para el banner
      setBridgeStatus("ready");
      setTimeout(onClose, 1200);
    } catch (e) {
      setError(mapBackendError(String(e)));
      // Si el backend dijo 503, también marcamos el bridge como down
      // para que el banner permanezco hasta el próximo retry.
      if (String(e).includes("503")) {
        setBridgeStatus("down");
      }
    } finally {
      setLoading(false);
    }
  }

  // close on backdrop click
  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
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

        {/* Aviso suave si el bridge está caído (no bloquea selección) */}
        {bridgeStatus === "down" && !error && (
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
          {filtered.length === 0 ? (
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
            disabled={!selected || loading || success}
          >
            {success ? "✓ Abriendo…" : loading ? "Enviando…" : "OK — Abrir en VS Code Chat"}
          </button>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef } from "react";
import type { VsCodeAgent, Ticket } from "../types";
import { Tickets } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentLaunchModal.module.css";

interface TicketComment { author: string; date: string; text: string; }

const BRIDGE_BASE = "http://localhost:5052";

interface AgentLaunchModalProps {
  agent: VsCodeAgent;
  avatarValue: string | null;
  onClose: () => void;
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
  const [bridgeError, setBridgeError] = useState(false);
  const [success, setSuccess] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // load tickets once
  useEffect(() => {
    Tickets.list().then((t) => {
      setTickets(t);
      setFiltered(t.slice(0, 20));
    }).catch(() => {});
    searchRef.current?.focus();
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

  async function handleLaunch() {
    if (!selected) return;
    setLoading(true);
    setBridgeError(false);

    // Build full ticket context so Copilot Chat receives more than just the title
    const parts: string[] = [`#ADO-${selected.ado_id} ${selected.title}`];
    const metaParts: string[] = [];
    if (selected.ado_state) metaParts.push(`Estado: **${selected.ado_state}**`);
    if (selected.priority != null) metaParts.push(`Prioridad: **${selected.priority}**`);
    if (selected.ado_url) metaParts.push(`[Ver en Azure DevOps](${selected.ado_url})`);
    if (metaParts.length) parts.push(metaParts.join(" | "));
    if (selected.description?.trim()) {
      parts.push(`\n## Descripción del ticket\n${selected.description.trim()}`);
    }
    if (comments.length) {
      const notesBlock = comments
        .map((c) => `**${c.author}** (${c.date}):\n${c.text}`)
        .join("\n\n---\n\n");
      parts.push(`\n## Notas / Comentarios del ticket\n${notesBlock}`);
    }
    if (message) parts.push(`\n## Mensaje adicional\n${message}`);
    const chatMessage = parts.join("\n\n");

    try {
      const res = await fetch(`${BRIDGE_BASE}/open-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: agent.filename,
          message: chatMessage,
        }),
      });
      if (!res.ok) throw new Error(`Bridge responded ${res.status}`);
      setSuccess(true);
      setTimeout(onClose, 1200);
    } catch {
      setBridgeError(true);
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

        {/* Error */}
        {bridgeError && (
          <div className={styles.error}>
            ⚠️ La extensión VS Code no está activa. Abrí VS Code con la extensión Stacky para continuar.
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

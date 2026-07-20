import React, { useState, useEffect } from "react";
import type { Ticket } from "../types";
import type { TicketAttachment } from "../api/endpoints";
import { Tickets } from "../api/endpoints";
import { Dialog } from "./ui";
import styles from "./FileSelectorModal.module.css";

interface FileSelectorModalProps {
  ticket: Ticket;
  prefix: string;
  agentName: string;
  loading?: boolean;
  onConfirm: (selectedFiles: string[]) => void;
  onCancel: () => void;
}

export default function FileSelectorModal({
  ticket,
  prefix,
  agentName,
  loading = false,
  onConfirm,
  onCancel,
}: FileSelectorModalProps) {
  const [attachments, setAttachments] = useState<TicketAttachment[]>([]);
  const [fetchLoading, setFetchLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    setFetchLoading(true);
    setFetchError(null);
    Tickets.attachments(ticket.id)
      .then((res) => {
        const data = (res as any).data ?? res;
        const all: TicketAttachment[] = data.attachments ?? [];
        const pfx = prefix.toLowerCase();
        const filtered = pfx
          ? all.filter((a) => a.name.toLowerCase().startsWith(pfx))
          : all;
        setAttachments(filtered);
        // Todos seleccionados por defecto
        setSelected(new Set(filtered.map((a) => a.name)));
        if (data.error) setFetchError(data.error);
      })
      .catch((err: unknown) => {
        setFetchError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setFetchLoading(false));
  }, [ticket.id, prefix]);

  function toggleAll() {
    if (selected.size === attachments.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(attachments.map((a) => a.name)));
    }
  }

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  const allSelected = attachments.length > 0 && selected.size === attachments.length;
  const noneSelected = selected.size === 0;

  return (
    <Dialog
      open
      onClose={onCancel}
      closeGuard={{ dirty: false, busy: loading }}
      ariaLabel="Seleccionar ficheros de entrada"
      size="md"
    >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerIcon}>📂</div>
          <div className={styles.headerText}>
            <span className={styles.title}>Seleccionar ficheros de entrada</span>
            <span className={styles.subtitle}>
              Agente: <strong>{agentName}</strong> · Ticket: <strong>#{ticket.ado_id}</strong>
            </span>
          </div>
          <button className={styles.closeBtn} onClick={onCancel} title="Cancelar">✕</button>
        </div>

        {/* Prefix badge */}
        <div className={styles.prefixRow}>
          <span className={styles.prefixLabel}>Prefijo configurado:</span>
          <span className={styles.prefixBadge}>{prefix || "(todos)"}</span>
          <span className={styles.modeBadge}>BATCH</span>
        </div>

        {/* Content */}
        <div className={styles.body}>
          {fetchLoading && (
            <div className={styles.centered}>
              <span className={styles.spinner} />
              Cargando adjuntos…
            </div>
          )}

          {!fetchLoading && fetchError && (
            <div className={styles.error}>⚠️ {fetchError}</div>
          )}

          {!fetchLoading && !fetchError && attachments.length === 0 && (
            <div className={styles.empty}>
              No hay ficheros adjuntos que empiecen por <strong>{prefix || "*"}</strong> en este ticket.
            </div>
          )}

          {!fetchLoading && !fetchError && attachments.length > 0 && (
            <>
              {/* Seleccionar todo */}
              <div className={styles.selectAll}>
                <label className={styles.checkRow}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className={styles.checkbox}
                  />
                  <span className={styles.selectAllLabel}>
                    Seleccionar todos ({attachments.length})
                  </span>
                </label>
              </div>

              {/* Lista de ficheros */}
              <div className={styles.fileList}>
                {attachments.map((att) => (
                  <label key={att.id} className={styles.fileRow}>
                    <input
                      type="checkbox"
                      checked={selected.has(att.name)}
                      onChange={() => toggle(att.name)}
                      className={styles.checkbox}
                    />
                    <span className={styles.fileName} title={att.name}>{att.name}</span>
                    <span className={styles.fileSize}>{formatSize(att.size)}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <span className={styles.selCount}>
            {selected.size} de {attachments.length} seleccionados
          </span>
          <div className={styles.actions}>
            <button className={styles.cancelBtn} onClick={onCancel} disabled={loading}>
              Cancelar
            </button>
            <button
              className={styles.confirmBtn}
              onClick={() => onConfirm(Array.from(selected))}
              disabled={loading || fetchLoading || noneSelected}
            >
              {loading ? "Enviando…" : `⚡ Ejecutar Batch (${selected.size})`}
            </button>
          </div>
        </div>
    </Dialog>
  );
}

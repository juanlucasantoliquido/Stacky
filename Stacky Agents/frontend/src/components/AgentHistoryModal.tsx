import React, { useEffect, useState } from "react";
import { Agents } from "../api/endpoints";
import type { AgentHistoryEntry, AgentHistoryResponse } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentHistoryModal.module.css";

interface AgentHistoryModalProps {
  filename: string;
  displayName: string;
  avatarValue: string | null;
  onClose: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  queued: "en cola",
  running: "ejecutando",
  completed: "completada",
  error: "con error",
  cancelled: "cancelada",
  discarded: "descartada",
};

const VERDICT_LABEL: Record<string, string> = {
  approved: "aprobado",
  discarded: "descartado",
};

export default function AgentHistoryModal({
  filename,
  displayName,
  avatarValue,
  onClose,
}: AgentHistoryModalProps) {
  const [data, setData] = useState<AgentHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Agents.history(filename, 50)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filename]);

  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div className={styles.backdrop} onClick={handleBackdrop}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Historial del agente">
        <div className={styles.header}>
          <PixelAvatar value={avatarValue} size="sm" name={displayName} />
          <div className={styles.headerText}>
            <span className={styles.agentName}>{displayName}</span>
            <span className={styles.subtitle}>Historial de tickets</span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">
            ✕
          </button>
        </div>

        {loading && <div className={styles.loading}>Cargando historial…</div>}

        {!loading && error && (
          <div className={styles.error}>
            ⚠️ No se pudo cargar el historial: {error}
          </div>
        )}

        {!loading && !error && data && (
          <>
            <div className={styles.metaBar}>
              <span className={styles.metaItem}>
                Tipo inferido: <strong>{data.inferred_agent_type}</strong>
              </span>
              <span className={styles.metaItem}>
                Total ejecuciones: <strong>{data.total_executions}</strong>
              </span>
            </div>

            {data.tickets.length === 0 ? (
              <EmptyHistory note={data.mapping_note} />
            ) : (
              <div className={styles.list}>
                {data.tickets.map((t) => (
                  <TicketRow key={t.ticket_id} entry={t} />
                ))}
              </div>
            )}

            <div className={styles.footnote}>{data.mapping_note}</div>
          </>
        )}
      </div>
    </div>
  );
}

function TicketRow({ entry }: { entry: AgentHistoryEntry }) {
  const verdict = entry.last_execution_verdict
    ? VERDICT_LABEL[entry.last_execution_verdict] ?? entry.last_execution_verdict
    : null;
  const statusLabel = STATUS_LABEL[entry.last_execution_status] ?? entry.last_execution_status;
  const verdictClass =
    entry.last_execution_verdict === "approved"
      ? styles.badgeOk
      : entry.last_execution_verdict === "discarded"
      ? styles.badgeBad
      : styles.badgeNeutral;

  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.ticketMeta}>
          <span className={styles.ticketId}>ADO-{entry.ado_id}</span>
          {entry.ado_state && <span className={styles.state}>{entry.ado_state}</span>}
        </div>
        <div className={styles.title} title={entry.title}>
          {entry.title}
        </div>
        <div className={styles.execMeta}>
          <span>
            Última ejecución #{entry.last_execution_id} · {statusLabel}
          </span>
          {entry.last_execution_started_at && (
            <span> · {new Date(entry.last_execution_started_at).toLocaleString()}</span>
          )}
          <span> · {entry.executions_count} ejecucione{entry.executions_count === 1 ? "" : "s"}</span>
        </div>
      </div>
      <div className={styles.rowSide}>
        {verdict && <span className={`${styles.badge} ${verdictClass}`}>{verdict}</span>}
        {entry.ado_url && (
          <a
            className={styles.adoLink}
            href={entry.ado_url}
            target="_blank"
            rel="noreferrer"
            title="Abrir en Azure DevOps"
          >
            ADO ↗
          </a>
        )}
      </div>
    </div>
  );
}

function EmptyHistory({ note }: { note: string }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>📭</div>
      <div className={styles.emptyTitle}>Sin historial todavía</div>
      <div className={styles.emptyText}>{note}</div>
    </div>
  );
}

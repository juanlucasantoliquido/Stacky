import React from "react";
import { Tickets, type TicketAttachment } from "../api/endpoints";
import ConfirmButton from "./ConfirmButton";
import { shouldCloseOnBackdrop } from "../services/uiGuards";
import styles from "./FileManagerModal.module.css";

interface Props {
  ticketId: number;
  ticketLabel: string;
  onClose: () => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FileManagerModal({ ticketId, ticketLabel, onClose }: Props) {
  const [attachments, setAttachments] = React.useState<TicketAttachment[] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [deleting, setDeleting] = React.useState(false);
  const [resultMsg, setResultMsg] = React.useState<{ text: string; isError: boolean } | null>(null);

  async function loadAttachments() {
    setLoading(true);
    setError(null);
    try {
      const res = await Tickets.attachments(ticketId);
      const data = (res as any).data ?? res;
      setAttachments(data.attachments ?? []);
      if (data.error) setError(data.error);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    loadAttachments();
  }, [ticketId]);

  function toggleFile(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (!attachments) return;
    if (selected.size === attachments.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(attachments.map((a) => a.id)));
    }
  }

  async function handleDelete() {
    if (!attachments || selected.size === 0) return;
    setDeleting(true);
    setResultMsg(null);
    const toDelete = attachments
      .filter((a) => selected.has(a.id))
      .map((a) => ({ id: a.id, url: a.url, name: a.name }));
    try {
      const res = await Tickets.deleteAttachments(ticketId, toDelete);
      const data = (res as any).data ?? res;
      const deleted: string[] = data.deleted ?? [];
      const errs: { id: string; name: string; error: string }[] = data.errors ?? [];
      let msg =
        `${deleted.length} adjunto${deleted.length !== 1 ? "s" : ""} borrado${deleted.length !== 1 ? "s" : ""}`;
      if (errs.length > 0) {
        // Si todos los errores tienen el mismo motivo, mostrarlo una vez
        const uniqueReasons = [...new Set(errs.map((e) => e.error))];
        const reasonText = uniqueReasons.length === 1
          ? ` — ${uniqueReasons[0]}`
          : ` — ${errs.map((e) => `${e.name}: ${e.error}`).join("; ")}`;
        msg += ` · ${errs.length} error${errs.length !== 1 ? "es" : ""}${reasonText}`;
      }
      setResultMsg({ text: msg, isError: errs.length > 0 });
      setSelected(new Set());
      await loadAttachments();
    } catch (e: any) {
      setResultMsg({ text: String(e?.message ?? e), isError: true });
    } finally {
      setDeleting(false);
    }
  }

  const allSelected = !!attachments && attachments.length > 0 && selected.size === attachments.length;

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty: selected.size > 0, busy: deleting })) onClose();
      }}
    >
      <div className={styles.modal}>
        <div className={styles.header}>
          <span className={styles.title}>
            Adjuntos del ticket{" "}
            <span className={styles.subtitle}>{ticketLabel}</span>
          </span>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">X</button>
        </div>

        {loading && <div className={styles.loading}>Cargando adjuntos...</div>}
        {!loading && error && <div className={styles.error}>{error}</div>}
        {!loading && attachments !== null && (
          <div className={styles.body}>
            {attachments.length > 0 && (
              <div className={styles.toolbar}>
                <button className={styles.selectAllBtn} onClick={toggleAll}>
                  {allSelected ? "Deseleccionar todo" : "Seleccionar todo"}
                </button>
                {selected.size > 0 && (
                  <span className={styles.selectedCount}>
                    {selected.size} seleccionado{selected.size !== 1 ? "s" : ""}
                  </span>
                )}
                <ConfirmButton
                  className={styles.deleteBtn}
                  label={deleting ? "Borrando..." : `Borrar (${selected.size})`}
                  confirmLabel={`⚠ Confirmar borrado (${selected.size})`}
                  disabled={selected.size === 0}
                  busy={deleting}
                  onConfirm={handleDelete}
                />
              </div>
            )}

            <div className={styles.fileList}>
              {attachments.length === 0 ? (
                <div className={styles.empty}>No hay adjuntos en este ticket.</div>
              ) : (
                attachments.map((a) => {
                  const isSel = selected.has(a.id);
                  return (
                    <div
                      key={a.id}
                      className={styles.fileRow + (isSel ? " " + styles.fileRowSelected : "")}
                      onClick={() => toggleFile(a.id)}
                    >
                      <input
                        type="checkbox"
                        className={styles.fileCheck}
                        checked={isSel}
                        onChange={() => toggleFile(a.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <span className={styles.fileName} title={a.name}>{a.name}</span>
                      <span className={styles.fileMeta}>
                        {formatSize(a.size)}
                        {a.created_at ? " " + new Date(a.created_at).toLocaleString() : ""}
                      </span>
                    </div>
                  );
                })
              )}
            </div>

            {resultMsg && (
              <div className={styles.resultMsg + (resultMsg.isError ? " " + styles.resultMsgError : "")}>
                {resultMsg.text}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

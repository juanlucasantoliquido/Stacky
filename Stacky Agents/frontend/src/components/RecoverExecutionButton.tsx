/**
 * RecoverExecutionButton — Botón "Cerrar ejecución y publicar".
 *
 * Visible cuando un ticket está en estado INCONSISTENTE:
 *   ticket.stacky_status == 'completed' AND hay una ejecución huérfana
 *   con status in {running, queued}.
 *
 * Flujo (plan §7.1, §7.2, §7.3):
 *   1. Click → llama al gateway con force=false.
 *   2. 200 → invalidar cache + toast verde.
 *   3. 409 html_already_published → diálogo de confirmación force=true.
 *      - Acepta → reintentar con force=true.
 *      - Rechaza → cerrar sin hacer nada.
 *   4. Otros 409/422 → toast de error con copy mapeado.
 *   5. 401/500 → toast genérico + console.error (sin stacktrace al usuario).
 *
 * Diseño: sigue el tema existente del repo (sin librerías UI nuevas).
 */
import { useState, useCallback, useId } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AgentCompletion, type AgentCompletionPayload } from "../api/endpoints";
import type { AgentExecution } from "../types";
import { getErrorInfo } from "../utils/agentCompletionErrors";
import Toast, { type ToastState } from "./Toast";
import styles from "./RecoverExecutionButton.module.css";

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  adoId: number;
  ticketId: number;
  /** La ejecución huérfana detectada (running|queued con stacky_status=completed). */
  orphanExecution: AgentExecution;
  /** Callback para que el padre limpie su estado visual si lo necesita. */
  onRecovered?: () => void;
  /** Compact: usado en el grafo (solo icono + texto corto). */
  compact?: boolean;
}

// ─── Diálogo de confirmación force=true ───────────────────────────────────────

interface ForceDialogProps {
  onAccept: () => void;
  onReject: () => void;
  isBusy: boolean;
}

function ForceConfirmDialog({ onAccept, onReject, isBusy }: ForceDialogProps) {
  return (
    <div className={styles.dialogOverlay} role="dialog" aria-modal="true" aria-labelledby="force-dialog-title">
      <div className={styles.dialog}>
        <h3 id="force-dialog-title" className={styles.dialogTitle}>
          HTML ya publicado
        </h3>
        <p className={styles.dialogBody}>
          Ya existe un comentario publicado para esta ejecución. Si continuas, se publicará el HTML actual en su lugar (forzado).
        </p>
        <p className={styles.dialogBody} style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, marginTop: 4 }}>
          Esta acción queda registrada en el audit log de Stacky.
        </p>
        <div className={styles.dialogActions}>
          <button className={styles.dialogCancel} onClick={onReject} disabled={isBusy}>
            Cancelar
          </button>
          <button className={styles.dialogConfirm} onClick={onAccept} disabled={isBusy}>
            {isBusy ? "Procesando..." : "Forzar publicación"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function RecoverExecutionButton({
  adoId,
  ticketId,
  orphanExecution,
  onRecovered,
  compact = false,
}: Props) {
  const qc = useQueryClient();
  const toastId = useId();

  const [isBusy, setIsBusy] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [showForceDialog, setShowForceDialog] = useState(false);

  const dismissToast = useCallback(() => setToast(null), []);

  /**
   * Llama al gateway de agent-completion.
   * Devuelve true si el cierre fue exitoso (200), false en cualquier otro caso.
   */
  const callGateway = useCallback(
    async (force: boolean): Promise<boolean> => {
      const payload: AgentCompletionPayload = {
        execution_id: orphanExecution.id,
        agent_type: orphanExecution.agent_type,
        status: "completed",
        html_output_path: orphanExecution.metadata?.html_output_path as string | undefined ?? null,
        metadata: {
          ...(orphanExecution.metadata ?? {}),
        },
        reason: "Recuperación manual desde UI",
        force,
      };

      const response = await AgentCompletion.complete(adoId, payload);

      if (response.ok && response.data) {
        // Éxito: invalidar cache y notificar al usuario
        qc.invalidateQueries({ queryKey: ["tickets"] });
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
        qc.invalidateQueries({ queryKey: ["executions-active"] });
        qc.invalidateQueries({ queryKey: ["executions-queued"] });
        qc.invalidateQueries({ queryKey: ["ticket-detail", ticketId] });

        setToast({
          variant: "success",
          title: "Ejecución cerrada",
          body: `La ejecución fue cerrada y publicada correctamente. (${response.data.result ?? "ok"})`,
          correlationId: response.data.correlation_id,
        });

        onRecovered?.();
        return true;
      }

      // Manejo de errores
      const code = response.errorBody?.error ?? "";
      const correlationId = response.errorBody?.correlation_id;

      if (response.status === 409 && code === "html_already_published") {
        // Este caso lo maneja el caller para mostrar el diálogo force
        return false;
      }

      // Errores conocidos mapeados a copy
      const info = getErrorInfo(code);

      if (response.status === 401 || response.status === 500) {
        // Error genérico para auth y errores internos — solo log a consola
        console.error("[RecoverExecution] Gateway error", {
          status: response.status,
          code,
          correlationId,
          body: response.errorBody,
        });
      }

      setToast({
        variant: info.severity === "error" ? "error" : "warning",
        title: info.title,
        body: info.body,
        correlationId,
      });

      return false;
    },
    [adoId, ticketId, orphanExecution, qc, onRecovered]
  );

  const handleClick = useCallback(async () => {
    if (isBusy) return;
    setIsBusy(true);
    setToast(null);

    try {
      const response = await AgentCompletion.complete(adoId, {
        execution_id: orphanExecution.id,
        agent_type: orphanExecution.agent_type,
        status: "completed",
        html_output_path: orphanExecution.metadata?.html_output_path as string | undefined ?? null,
        metadata: { ...(orphanExecution.metadata ?? {}) },
        reason: "Recuperación manual desde UI",
        force: false,
      });

      if (response.ok && response.data) {
        qc.invalidateQueries({ queryKey: ["tickets"] });
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
        qc.invalidateQueries({ queryKey: ["executions-active"] });
        qc.invalidateQueries({ queryKey: ["executions-queued"] });
        qc.invalidateQueries({ queryKey: ["ticket-detail", ticketId] });

        setToast({
          variant: "success",
          title: "Ejecución cerrada",
          body: `La ejecución fue cerrada y publicada. (${response.data.result ?? "ok"})`,
          correlationId: response.data.correlation_id,
        });

        onRecovered?.();
        return;
      }

      const code = response.errorBody?.error ?? "";
      const correlationId = response.errorBody?.correlation_id;

      if (response.status === 409 && code === "html_already_published") {
        // Mostrar diálogo de confirmación force=true
        setShowForceDialog(true);
        return;
      }

      if (response.status === 401 || response.status === 500) {
        console.error("[RecoverExecution] Gateway error", {
          status: response.status,
          code,
          correlationId,
          body: response.errorBody,
        });
      }

      const info = getErrorInfo(code);
      setToast({
        variant: info.severity === "error" ? "error" : "warning",
        title: info.title,
        body: info.body,
        correlationId,
      });
    } finally {
      setIsBusy(false);
    }
  }, [adoId, ticketId, orphanExecution, qc, onRecovered, isBusy]);

  const handleForceAccept = useCallback(async () => {
    setIsBusy(true);
    try {
      await callGateway(true);
    } finally {
      setIsBusy(false);
      setShowForceDialog(false);
    }
  }, [callGateway]);

  const handleForceReject = useCallback(() => {
    setShowForceDialog(false);
  }, []);

  return (
    <>
      <button
        className={`${styles.recoverBtn} ${compact ? styles.recoverBtnCompact : ""}`}
        onClick={handleClick}
        disabled={isBusy}
        title="Cerrar la ejecución huérfana y publicar en ADO"
        aria-label="Cerrar ejecución y publicar"
      >
        {isBusy
          ? (compact ? "..." : "Procesando...")
          : (compact ? "Recuperar" : "Cerrar ejecución y publicar")}
      </button>

      {showForceDialog && (
        <ForceConfirmDialog
          onAccept={handleForceAccept}
          onReject={handleForceReject}
          isBusy={isBusy}
        />
      )}

      {toast && <Toast toast={toast} onClose={dismissToast} />}
    </>
  );
}

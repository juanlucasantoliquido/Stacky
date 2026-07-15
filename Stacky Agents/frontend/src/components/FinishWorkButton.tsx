/**
 * FinishWorkButton — Cierre manual fallback (Fase 4 del plan ADO delegation).
 *
 * Visible cuando un ticket NO está en stacky_status='completed' y tampoco está
 * en un ado_state cerrado. Permite al operador:
 *   1. Hacer dry-run para ver precondiciones (HTML existe, status actual).
 *   2. Confirmar el cierre, que dispara: publish HTML → update ADO state →
 *      marcar stacky_status='completed' → registrar audit en system_logs.
 *
 * Diseño UX:
 *   - Primer click abre modal con campos y muestra dry-run automático al abrir.
 *   - El usuario revisa precondiciones, escribe motivo, confirma.
 *   - Cada acción del backend se muestra con su ok/reason individual.
 */
import { useState, useCallback, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Tickets, type FinishWorkResponse } from "../api/endpoints";
import type { Ticket } from "../types";
import { useWorkbench } from "../store/workbench";
import { shouldCloseOnBackdrop } from "../services/uiGuards";
import styles from "./FinishWorkButton.module.css";

interface Props {
  ticket: Ticket;
  /** Si true, el botón sigue visible pero queda deshabilitado (ej. hay agente corriendo). */
  disabled?: boolean;
  /** Callback opcional al completar exitosamente — útil para refrescar la lista. */
  onCompleted?: () => void;
}

export default function FinishWorkButton({ ticket, disabled, onCompleted }: Props) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [publishToAdo, setPublishToAdo] = useState(true);
  const [targetState, setTargetState] = useState("");

  // B2 (fix secundario): pre-cargar el estado destino con el `transition_state`
  // configurado para el agente activo, en vez de un string vacío. Así el cierre
  // manual respeta por default el mismo estado que aplica el cierre automático.
  const vsCodeAgent = useWorkbench((s) => s.vsCodeAgent);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const configuredTransitionState = vsCodeAgent
    ? (agentWorkflows[vsCodeAgent.filename]?.transition_state ?? "")
    : "";
  const [forcePublish, setForcePublish] = useState(false);
  const [lastResult, setLastResult] = useState<FinishWorkResponse | null>(null);
  const [confirming, setConfirming] = useState(false);

  const dryRunMutation = useMutation({
    mutationFn: () =>
      Tickets.finishWork(ticket.id, {
        operator_reason: reason.trim() || "(dry-run preview)",
        publish_to_ado: publishToAdo,
        target_ado_state: targetState.trim() || null,
        dry_run: true,
      }),
    onSuccess: (data) => setLastResult(data),
  });

  const finalMutation = useMutation({
    mutationFn: () =>
      Tickets.finishWork(ticket.id, {
        operator_reason: reason.trim(),
        publish_to_ado: publishToAdo,
        target_ado_state: targetState.trim() || null,
        force_publish: forcePublish,
        dry_run: false,
        cancel_active_execution: true,
      }),
    onSuccess: (data) => {
      setLastResult(data);
      setConfirming(false);
      if (data.ok) onCompleted?.();
    },
  });

  // Auto-dry-run al abrir el modal (con motivo placeholder), para enseñar al
  // operador las precondiciones antes de que escriba nada.
  useEffect(() => {
    if (open && !lastResult && !dryRunMutation.isPending) {
      dryRunMutation.mutate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // B2: al abrir, sembrar el estado destino con el transition_state configurado
  // (si lo hay y el operador no escribió otro todavía).
  useEffect(() => {
    if (open && configuredTransitionState && !targetState) {
      setTargetState(configuredTransitionState);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = useCallback(() => {
    setOpen(false);
    setReason("");
    setTargetState("");
    setPublishToAdo(true);
    setForcePublish(false);
    setLastResult(null);
    setConfirming(false);
  }, []);

  const reasonValid = reason.trim().length >= 5;
  const canConfirm = reasonValid && !finalMutation.isPending;
  const isBusy = dryRunMutation.isPending || finalMutation.isPending;

  return (
    <>
      <button
        className={styles.btn}
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        disabled={disabled}
        title={
          disabled
            ? "Hay un agente corriendo — esperá a que termine o cancelalo"
            : "Forzar cierre manual del ticket (publica HTML del agente y cambia estado)"
        }
      >
        🏁 Terminar trabajo
      </button>

      {open && (
        <div
          className={styles.overlay}
          onClick={() => {
            if (shouldCloseOnBackdrop({ dirty: reason.trim().length > 0, busy: isBusy })) handleClose();
          }}
        >
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <header className={styles.header}>
              <h3 className={styles.title}>Terminar trabajo manualmente</h3>
              <button className={styles.close} onClick={handleClose} disabled={isBusy}>✕</button>
            </header>

            <div className={styles.sub}>
              <span className={styles.adoTag}>ADO-{ticket.ado_id}</span>
              <span className={styles.ticketTitle}>{ticket.title}</span>
            </div>

            {/* Precondiciones (dry-run) */}
            <section className={styles.section}>
              <h4 className={styles.h4}>Precondiciones</h4>
              {dryRunMutation.isPending && (
                <p className={styles.muted}>Verificando estado…</p>
              )}
              {lastResult && (
                <ul className={styles.preconds}>
                  <li>
                    <span className={styles.checkLabel}>HTML del agente en disco:</span>{" "}
                    <span className={lastResult.preconditions.html_exists ? styles.ok : styles.warn}>
                      {lastResult.preconditions.html_exists
                        ? "✓ presente"
                        : "✗ no encontrado (se publicará nota de cierre manual)"}
                    </span>
                  </li>
                  {lastResult.preconditions.html_invalid_reason && (
                    <li>
                      <span className={styles.checkLabel}>Motivo:</span>{" "}
                      <span className={styles.warn}>
                        {lastResult.preconditions.html_invalid_reason}
                      </span>
                    </li>
                  )}
                  <li>
                    <span className={styles.checkLabel}>stacky_status actual:</span>{" "}
                    <code>{lastResult.preconditions.current_stacky_status}</code>
                  </li>
                  <li>
                    <span className={styles.checkLabel}>Última ejecución:</span>{" "}
                    {lastResult.preconditions.execution_id !== null
                      ? <code>#{lastResult.preconditions.execution_id}</code>
                      : <span className={styles.warn}>ninguna</span>}
                  </li>
                </ul>
              )}
              {/* CA-5.1: advertencia de ejecución activa detectada en dry-run */}
              {lastResult?.preconditions.active_execution && (
                <p className={styles.activeExecWarning}>
                  Ejecucion activa: #{lastResult.preconditions.active_execution.execution_id}{" "}
                  ({lastResult.preconditions.active_execution.agent_type}) — se cancelara antes del cierre
                </p>
              )}
            </section>

            {/* Formulario */}
            <section className={styles.section}>
              <label className={styles.label}>
                Motivo del cierre manual <span className={styles.req}>(obligatorio, min 5 chars)</span>
              </label>
              <textarea
                className={styles.textarea}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Ej: El agente terminó pero Stacky no recibió la señal por timeout"
                rows={3}
                disabled={isBusy}
                autoFocus
              />

              <label className={styles.inlineLabel}>
                <input
                  type="checkbox"
                  checked={publishToAdo}
                  onChange={(e) => setPublishToAdo(e.target.checked)}
                  disabled={isBusy}
                />{" "}
                Publicar comentario en ADO
              </label>

              <label className={styles.label}>
                Estado destino en ADO <span className={styles.opt}>(opcional)</span>
              </label>
              <input
                type="text"
                className={styles.input}
                value={targetState}
                onChange={(e) => setTargetState(e.target.value)}
                placeholder="Ej: Done, Closed, Resolved"
                disabled={isBusy}
                list="ado-state-suggestions"
              />
              <datalist id="ado-state-suggestions">
                <option value="Done" />
                <option value="Closed" />
                <option value="Resolved" />
                <option value="Active" />
              </datalist>

              <label className={styles.inlineLabel}>
                <input
                  type="checkbox"
                  checked={forcePublish}
                  onChange={(e) => setForcePublish(e.target.checked)}
                  disabled={isBusy}
                />{" "}
                Forzar re-publicación (ignorar dedupe por hash)
              </label>
            </section>

            {/* Resultado de acciones (cuando ya se ejecutó el cierre real) */}
            {lastResult && !lastResult.dry_run && lastResult.actions.length > 0 && (
              <section className={styles.section}>
                <h4 className={styles.h4}>Resultado</h4>
                <ul className={styles.actions}>
                  {lastResult.actions.map((a, i) => (
                    <li key={i} className={a.ok ? styles.actionOk : styles.actionFail}>
                      <span className={styles.actionIcon}>{a.ok ? "✓" : "✗"}</span>
                      <span className={styles.actionName}>{a.action}</span>
                      {a.to && <code className={styles.actionTo}>{a.to}</code>}
                      {a.reason && <span className={styles.actionReason}>{a.reason}</span>}
                    </li>
                  ))}
                </ul>
                {/* CA-5.2 / CA-5.3: resultado de cancelación de ejecución activa */}
                {lastResult.cancel_result != null && (
                  lastResult.cancel_result.cancel_ok ? (
                    <p className={styles.cancelResultOk}>
                      Cancelacion: OK (ejecucion #{lastResult.cancel_result.execution_id}{" "}
                      — {lastResult.cancel_result.agent_type})
                    </p>
                  ) : (
                    <p className={styles.cancelResultFail}>
                      Cancelacion fallo: {lastResult.cancel_result.cancel_reason ?? "razon desconocida"}.
                      El cierre se ejecuto igualmente.
                    </p>
                  )
                )}
                {/* CA-5.4: si cancel_result es null, no se muestra nada (sin ejecución activa) */}
              </section>
            )}

            {finalMutation.isError && (
              <p className={styles.errorMsg}>
                ⚠ Error al ejecutar cierre: {(finalMutation.error as Error)?.message}
              </p>
            )}
            {dryRunMutation.isError && (
              <p className={styles.errorMsg}>
                ⚠ Error al validar: {(dryRunMutation.error as Error)?.message}
              </p>
            )}

            <footer className={styles.footer}>
              <button
                className={styles.cancel}
                onClick={handleClose}
                disabled={isBusy}
              >
                Cerrar
              </button>
              {!confirming ? (
                <button
                  className={styles.danger}
                  onClick={() => setConfirming(true)}
                  disabled={!canConfirm}
                  title={
                    !reasonValid
                      ? "Ingresá un motivo de al menos 5 caracteres"
                      : "Cerrar el ticket ahora"
                  }
                >
                  🏁 Terminar trabajo
                </button>
              ) : (
                <button
                  className={styles.dangerConfirm}
                  onClick={() => finalMutation.mutate()}
                  disabled={finalMutation.isPending}
                >
                  {finalMutation.isPending
                    ? "⏳ Procesando…"
                    : "⚠ Confirmar cierre"}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}
    </>
  );
}

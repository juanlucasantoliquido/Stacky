/**
 * DataReadinessModal.tsx — Sprint 9: Data Readiness UI
 *
 * Shows pending data resolution requests for a QA UAT run.
 * Allows operators to:
 *   1. Provide an existing value (e.g. CLCOD)
 *   2. Request SQL seed generation
 *   3. Mark as manual review
 *
 * Props:
 *   runId      — pipeline run identifier (used to locate qa_data_requests.json)
 *   ticketId   — ADO ticket ID (int)
 *   onClose    — close handler
 *   onResolved — called when all pending requests are resolved (triggers pipeline resume)
 *
 * Security:
 *   - Prompt injection check is done server-side (user_data_validator.py).
 *   - No raw PII is rendered; masked values come from the server.
 */
import React, { useState, useEffect, useCallback } from "react";
import { QaUat } from "../api/endpoints";
import type { DataRequest } from "../api/endpoints";
import { Dialog } from "./ui";
import styles from "./DataReadinessModal.module.css";

interface Props {
  runId: string;
  ticketId: number;
  onClose: () => void;
  onResolved?: () => void;
}

type ActiveForm = {
  requestId: string;
  fields: Record<string, string>;
};

type ValidationState = {
  requestId: string;
  valid: boolean;
  message: string;
};

export default function DataReadinessModal({ runId, ticketId, onClose, onResolved }: Props) {
  const [requests, setRequests] = useState<DataRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeForm, setActiveForm] = useState<ActiveForm | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);  // request_id being submitted
  const [validationResults, setValidationResults] = useState<Record<string, ValidationState>>({});
  // Per-request resolution artifacts (decisions with questions/options)
  const [artifacts, setArtifacts] = useState<Record<string, unknown>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await QaUat.listDataRequests(runId, ticketId);
      setRequests(res.requests);
      setArtifacts(res.resolution_artifacts ?? {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [runId, ticketId]);

  useEffect(() => {
    load();
  }, [load]);

  const pendingCount = requests.filter((r) => r.status === "pending_user_input").length;

  function getRequiredFields(req: DataRequest): string[] {
    try {
      return JSON.parse(req.required_fields_json) as string[];
    } catch {
      return [];
    }
  }

  function initForm(req: DataRequest) {
    const fields = getRequiredFields(req);
    setActiveForm({
      requestId: req.id,
      fields: Object.fromEntries(fields.map((f) => [f, ""])),
    });
    setValidationResults((prev) => {
      const next = { ...prev };
      delete next[req.id];
      return next;
    });
  }

  function cancelForm() {
    setActiveForm(null);
  }

  async function submitValue(req: DataRequest) {
    if (!activeForm || activeForm.requestId !== req.id) return;
    const fields = getRequiredFields(req);
    const empty = fields.find((f) => !activeForm.fields[f]?.trim());
    if (empty) {
      setValidationResults((prev) => ({
        ...prev,
        [req.id]: { requestId: req.id, valid: false, message: `El campo ${empty} es obligatorio.` },
      }));
      return;
    }

    setSubmitting(req.id);
    try {
      const res = await QaUat.resolveDataRequest(req.id, {
        resolution_type: "provide_existing_value",
        supplied_fields: activeForm.fields,
        run_id: runId,
        ticket_id: ticketId,
        scenario_id: req.scenario_id,
      });

      if (res.ok && res.result?.validation?.valid !== false) {
        setValidationResults((prev) => ({
          ...prev,
          [req.id]: { requestId: req.id, valid: true, message: "Dato válido. Solicitud resuelta." },
        }));
        setActiveForm(null);
        await load();
      } else {
        const msg = res.message || (res.result?.validation?.valid === false
          ? "El valor no cumple los requisitos del escenario."
          : "Error al resolver la solicitud.");
        setValidationResults((prev) => ({
          ...prev,
          [req.id]: { requestId: req.id, valid: false, message: msg },
        }));
      }
    } catch (e: unknown) {
      setValidationResults((prev) => ({
        ...prev,
        [req.id]: {
          requestId: req.id,
          valid: false,
          message: e instanceof Error ? e.message : "Error inesperado. Revisá los logs.",
        },
      }));
    } finally {
      setSubmitting(null);
    }
  }

  async function markManualReview(req: DataRequest) {
    setSubmitting(req.id);
    try {
      await QaUat.resolveDataRequest(req.id, {
        resolution_type: "manual_review",
        run_id: runId,
        ticket_id: ticketId,
        scenario_id: req.scenario_id,
      });
      setActiveForm(null);
      await load();
    } catch (e: unknown) {
      setValidationResults((prev) => ({
        ...prev,
        [req.id]: {
          requestId: req.id,
          valid: false,
          message: e instanceof Error ? e.message : "Error al marcar revisión manual.",
        },
      }));
    } finally {
      setSubmitting(null);
    }
  }

  async function requestSqlSeed(req: DataRequest) {
    setSubmitting(req.id);
    try {
      await QaUat.resolveDataRequest(req.id, {
        resolution_type: "generate_sql_seed",
        run_id: runId,
        ticket_id: ticketId,
        scenario_id: req.scenario_id,
      });
      setActiveForm(null);
      await load();
    } catch (e: unknown) {
      setValidationResults((prev) => ({
        ...prev,
        [req.id]: {
          requestId: req.id,
          valid: false,
          message: e instanceof Error ? e.message : "Error al solicitar SQL seed.",
        },
      }));
    } finally {
      setSubmitting(null);
    }
  }

  // Notify parent when all pending requests are resolved
  useEffect(() => {
    if (!loading && requests.length > 0 && pendingCount === 0 && onResolved) {
      onResolved();
    }
  }, [loading, requests, pendingCount, onResolved]);

  function statusClass(status: string) {
    if (status === "resolved") return styles.statusResolved;
    if (status === "timeout") return styles.statusTimeout;
    return styles.statusPending;
  }

  function statusLabel(status: string) {
    if (status === "resolved") return "Resuelto";
    if (status === "timeout") return "Expirado";
    return "Pendiente";
  }

  function getQuestion(req: DataRequest): string {
    // Try to get question from resolution artifact (broker output)
    const art = artifacts[req.scenario_id] as { decisions?: { request_id: string; question_for_user: string }[] } | undefined;
    if (art?.decisions) {
      const decision = art.decisions.find((d) => d.request_id === req.id);
      if (decision?.question_for_user) return decision.question_for_user;
    }
    return req.question || "Se requieren datos para ejecutar este escenario.";
  }

  function getOptions(req: DataRequest): { id: string; label: string; requires_input: string[] }[] {
    const art = artifacts[req.scenario_id] as { decisions?: { request_id: string; options: { id: string; label: string; requires_input: string[] }[] }[] } | undefined;
    if (art?.decisions) {
      const decision = art.decisions.find((d) => d.request_id === req.id);
      if (decision?.options) return decision.options;
    }
    // Fallback options
    const fields = getRequiredFields(req);
    return [
      { id: "provide_existing_value", label: `Ingresar ${fields.join(", ") || "valor"} existente`, requires_input: fields },
      { id: "manual_review", label: "Marcar como revisión manual", requires_input: [] },
    ];
  }

  return (
    <Dialog open onClose={onClose} ariaLabel="Data Readiness" size="lg">
        {/* Header */}
        <div className={styles.header}>
          <span className={styles.headerIcon}>🔒</span>
          <span className={styles.headerTitle}>Datos faltantes — QA UAT</span>
          {pendingCount > 0 ? (
            <span className={styles.badgePending}>{pendingCount} pendiente{pendingCount > 1 ? "s" : ""}</span>
          ) : (
            !loading && <span className={styles.badgeResolved}>Todo resuelto</span>
          )}
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
        </div>

        {/* Body */}
        <div className={styles.body}>
          {loading && (
            <div className={styles.emptyState}>
              <div className={styles.spinner} style={{ margin: "0 auto 0.5rem" }} />
              Cargando solicitudes de datos...
            </div>
          )}

          {error && !loading && (
            <div className={styles.validationResult + " " + styles.validationError}>
              Error al cargar solicitudes: {error}
            </div>
          )}

          {!loading && !error && requests.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>✅</div>
              No hay solicitudes de datos pendientes para este run.
            </div>
          )}

          {!loading && requests.length > 0 && (
            <>
              {/* Context info */}
              <div className={styles.contextInfo}>
                <strong>Run: {runId} · Ticket #{ticketId}</strong>
                El pipeline detectó {requests.length} requisito{requests.length > 1 ? "s" : ""} de datos.
                Resolvé cada solicitud para que el agente pueda continuar la ejecución UAT.
              </div>

              {/* Request cards */}
              {requests.map((req) => {
                const fields = getRequiredFields(req);
                const question = getQuestion(req);
                const options = getOptions(req);
                const isResolved = req.status !== "pending_user_input";
                const isSubmittingThis = submitting === req.id;
                const validation = validationResults[req.id];
                const isShowingForm = activeForm?.requestId === req.id;

                return (
                  <div
                    key={req.id}
                    className={`${styles.requestCard} ${isResolved ? styles.isResolved : ""}`}
                  >
                    {/* Card header */}
                    <div className={styles.requestHeader}>
                      <span className={styles.requestScenario}>{req.scenario_id}</span>
                      <span className={`${styles.requestStatus} ${statusClass(req.status)}`}>
                        {statusLabel(req.status)}
                      </span>
                    </div>

                    {/* Card body */}
                    <div className={styles.requestBody}>
                      <p className={styles.question}>{question}</p>

                      {/* Required fields chips */}
                      {fields.length > 0 && (
                        <div className={styles.requiredFields}>
                          <span className={styles.requiredFieldsLabel}>Campos requeridos:</span>
                          {fields.map((f) => (
                            <span key={f} className={styles.fieldTag}>{f}</span>
                          ))}
                        </div>
                      )}

                      {/* Resolved info */}
                      {isResolved && (
                        <div className={styles.resolvedInfo}>
                          ✓ Resuelto como &ldquo;{req.resolution_type}&rdquo;
                          {req.resolved_by ? ` por ${req.resolved_by}` : ""}
                          {req.resolved_at ? ` — ${new Date(req.resolved_at).toLocaleString()}` : ""}
                        </div>
                      )}

                      {/* Options (only for pending) */}
                      {!isResolved && !isShowingForm && (
                        <div className={styles.options}>
                          {options.map((opt) => {
                            if (opt.requires_input.length > 0) {
                              return (
                                <button
                                  key={opt.id}
                                  className={`${styles.optionBtn} ${styles.optionBtnPrimary}`}
                                  onClick={() => initForm(req)}
                                  disabled={isSubmittingThis}
                                >
                                  {isSubmittingThis && <span className={styles.spinner} />}
                                  📝 {opt.label}
                                </button>
                              );
                            }
                            if (opt.id === "generate_sql_seed") {
                              return (
                                <button
                                  key={opt.id}
                                  className={styles.optionBtn}
                                  onClick={() => requestSqlSeed(req)}
                                  disabled={isSubmittingThis}
                                >
                                  {isSubmittingThis && <span className={styles.spinner} />}
                                  🗄 {opt.label}
                                </button>
                              );
                            }
                            if (opt.id === "manual_review") {
                              return (
                                <button
                                  key={opt.id}
                                  className={styles.optionBtn}
                                  onClick={() => markManualReview(req)}
                                  disabled={isSubmittingThis}
                                >
                                  {isSubmittingThis && <span className={styles.spinner} />}
                                  🙋 {opt.label}
                                </button>
                              );
                            }
                            return (
                              <button
                                key={opt.id}
                                className={styles.optionBtn}
                                disabled={isSubmittingThis}
                              >
                                {opt.label}
                              </button>
                            );
                          })}
                        </div>
                      )}

                      {/* Inline input form */}
                      {!isResolved && isShowingForm && activeForm && (
                        <div className={styles.inputForm}>
                          {Object.keys(activeForm.fields).map((fieldName) => (
                            <div key={fieldName}>
                              <div className={styles.inputLabel}>{fieldName}</div>
                              <div className={styles.inputRow}>
                                <input
                                  className={`${styles.inputField} ${
                                    validation && !validation.valid ? styles.invalid : ""
                                  }`}
                                  type="text"
                                  placeholder={`Ingresá ${fieldName}...`}
                                  value={activeForm.fields[fieldName]}
                                  onChange={(e) =>
                                    setActiveForm((prev) =>
                                      prev
                                        ? {
                                            ...prev,
                                            fields: { ...prev.fields, [fieldName]: e.target.value },
                                          }
                                        : null
                                    )
                                  }
                                  onKeyDown={(e) => e.key === "Enter" && submitValue(req)}
                                  disabled={isSubmittingThis}
                                  autoFocus
                                />
                                <button
                                  className={styles.submitBtn}
                                  onClick={() => submitValue(req)}
                                  disabled={isSubmittingThis || !activeForm.fields[fieldName]?.trim()}
                                >
                                  {isSubmittingThis ? <span className={styles.spinner} /> : "Validar"}
                                </button>
                              </div>
                            </div>
                          ))}
                          <button
                            className={styles.cancelBtn}
                            onClick={cancelForm}
                            disabled={isSubmittingThis}
                          >
                            Cancelar
                          </button>
                        </div>
                      )}

                      {/* Validation feedback */}
                      {validation && (
                        <div
                          className={`${styles.validationResult} ${
                            validation.valid ? styles.validationOk : styles.validationError
                          }`}
                        >
                          {validation.valid ? "✓ " : "✗ "}{validation.message}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <span className={styles.footerInfo}>
            {pendingCount > 0
              ? `${pendingCount} solicitud${pendingCount > 1 ? "es" : ""} pendiente${pendingCount > 1 ? "s" : ""} de resolución`
              : "Todas las solicitudes están resueltas"}
          </span>
          <button className={styles.cancelBtn} onClick={onClose}>
            Cerrar
          </button>
        </div>
    </Dialog>
  );
}

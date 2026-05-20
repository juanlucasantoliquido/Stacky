/**
 * AssignmentRecommendationPanel — Panel de recomendacion de asignacion P6.
 *
 * Human-in-the-loop obligatorio:
 * 1. El operador solicita recomendaciones.
 * 2. Ve la lista de candidatos con scores y razones explicables.
 * 3. Selecciona un candidato.
 * 4. Ve un preview (dry_run) de lo que se cambiara en ADO.
 * 5. Confirma explicitamente (boton "Confirmar asignacion").
 * 6. Solo entonces se llama a POST /api/tickets/{id}/assign con dry_run=false.
 *
 * advisory_only: el panel nunca aplica nada sin confirmacion del operador.
 */

import React, { useState, useCallback } from "react";
import type { Ticket } from "../types";
import styles from "./AssignmentRecommendationPanel.module.css";

interface AssignmentCandidate {
  ado_unique_name: string;
  display_name: string;
  score: number;
  rank: number;
  overloaded: boolean;
  load_pct: number;
  active_tickets: number;
  reason: string;
  recommendation_flags: string[];
  type_affinity: { score: number; top_types: string[]; match: boolean };
  area_affinity: { score: number; matched_areas: string[] };
  throughput_score: number;
}

interface DryRunResult {
  would_assign_to: string;
  current_assigned: string | null;
  ticket_ado_id: number;
  actions: { action: string; would_call: string }[];
}

type Phase =
  | "idle"
  | "loading"
  | "recommendations"
  | "confirming"
  | "applying"
  | "done"
  | "error";

interface AssignmentRecommendationPanelProps {
  ticket: Ticket;
  onAssigned: () => void;
}

const API_BASE = (window as any).__STACKY_API_BASE__ ?? "";

async function fetchJson(url: string, opts?: RequestInit) {
  const resp = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  return resp.json();
}

export function AssignmentRecommendationPanel({
  ticket,
  onAssigned,
}: AssignmentRecommendationPanelProps): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [candidates, setCandidates] = useState<AssignmentCandidate[]>([]);
  const [selected, setSelected] = useState<AssignmentCandidate | null>(null);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleOpen = useCallback(async () => {
    setOpen(true);
    setPhase("loading");
    setError(null);
    setCandidates([]);
    setSelected(null);
    setDryRunResult(null);

    try {
      const data = await fetchJson(`/api/tickets/${ticket.id}/assignment-recommendations`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!data.ok) {
        setError(data.message || data.error || "Error al cargar recomendaciones");
        setPhase("error");
        return;
      }
      if (data.error === "no_users_configured") {
        setError("No hay usuarios configurados. Ejecuta 'Sincronizar usuarios desde ADO' primero.");
        setPhase("error");
        return;
      }
      setCandidates(data.candidates || []);
      setPhase("recommendations");
    } catch (e: any) {
      setError(e.message || "Error de red");
      setPhase("error");
    }
  }, [ticket.id]);

  const handleSelectCandidate = useCallback(async (candidate: AssignmentCandidate) => {
    setSelected(candidate);
    setPhase("confirming");
    setError(null);

    // Dry-run preview
    try {
      const data = await fetchJson(`/api/tickets/${ticket.id}/assign`, {
        method: "POST",
        body: JSON.stringify({ ado_unique_name: candidate.ado_unique_name, dry_run: true }),
      });
      if (data.ok) {
        setDryRunResult(data);
      } else {
        setError(data.message || "Error en preview");
      }
    } catch (e: any) {
      setError(e.message || "Error de red en preview");
    }
  }, [ticket.id]);

  const handleConfirm = useCallback(async () => {
    if (!selected) return;
    setPhase("applying");
    setError(null);

    try {
      const data = await fetchJson(`/api/tickets/${ticket.id}/assign`, {
        method: "POST",
        body: JSON.stringify({
          ado_unique_name: selected.ado_unique_name,
          dry_run: false,
          reason: `Asignado por recomendacion Stacky — score ${selected.score.toFixed(2)}`,
        }),
      });
      if (data.ok && data.ado_updated) {
        setPhase("done");
        onAssigned();
      } else {
        setError(data.message || "Error al aplicar asignacion en ADO");
        setPhase("confirming");
      }
    } catch (e: any) {
      setError(e.message || "Error de red al aplicar");
      setPhase("confirming");
    }
  }, [selected, ticket.id, onAssigned]);

  const handleClose = useCallback(() => {
    setOpen(false);
    setPhase("idle");
    setSelected(null);
    setError(null);
    setDryRunResult(null);
  }, []);

  // Solo mostrar el boton si el ticket no tiene asignado
  const showButton = !ticket.assigned_to_ado;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span>Asignacion</span>
        {ticket.assigned_to_ado ? (
          <span style={{ color: "#6b7280", fontWeight: "normal" }}>
            Asignado: {ticket.assigned_to_ado}
          </span>
        ) : (
          !open && (
            <button className={styles.openBtn} onClick={handleOpen}>
              Sugerir asignacion
            </button>
          )
        )}
      </div>

      {open && (
        <div className={styles.body}>
          {phase === "loading" && (
            <div className={styles.loading}>Calculando recomendaciones...</div>
          )}

          {phase === "error" && (
            <>
              {error?.includes("no hay usuarios") || error?.includes("no_users_configured") ? (
                <div className={styles.noUsers}>
                  {error}
                  <br />
                  <small>
                    Usa el boton de sincronizacion de usuarios o configura manualmente en la BD.
                  </small>
                </div>
              ) : (
                <div className={styles.error}>{error}</div>
              )}
              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button className={styles.btnSecondary} onClick={handleOpen}>
                  Reintentar
                </button>
                <button className={styles.btnSecondary} onClick={handleClose}>
                  Cerrar
                </button>
              </div>
            </>
          )}

          {phase === "recommendations" && (
            <>
              {candidates.length === 0 ? (
                <div className={styles.loading}>
                  No hay candidatos disponibles con los filtros actuales.
                </div>
              ) : (
                <div className={styles.candidateList}>
                  {candidates.map((c) => (
                    <div
                      key={c.ado_unique_name}
                      className={[
                        styles.candidateCard,
                        c.overloaded ? styles.overloaded : "",
                      ].join(" ")}
                      onClick={() => !c.overloaded && handleSelectCandidate(c)}
                    >
                      <div className={styles.candidateInfo}>
                        <div className={styles.candidateName}>{c.display_name}</div>
                        <div className={styles.candidateMeta}>
                          {c.active_tickets} tickets activos &middot; Carga: {c.load_pct.toFixed(0)}%
                          {c.type_affinity.match && (
                            <> &middot; Especialista en {ticket.work_item_type}</>
                          )}
                        </div>
                        <div className={styles.candidateReason}>{c.reason}</div>
                        {c.recommendation_flags.includes("overloaded") && (
                          <span className={styles.badge}>Sobrecargado</span>
                        )}
                        {c.recommendation_flags.includes("no_type_specialization") && (
                          <span className={styles.badgeWarn}>Sin especializacion en tipo</span>
                        )}
                      </div>
                      <div className={styles.scoreBar}>
                        <div className={styles.rank}>#{c.rank}</div>
                        <div className={styles.scoreValue}>{(c.score * 100).toFixed(0)}%</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className={styles.advisory}>
                Recomendacion solo consultiva (advisory_only). La asignacion requiere
                confirmacion explicita del operador antes de escribir en ADO.
              </div>
              <button
                className={styles.btnSecondary}
                style={{ marginTop: 10 }}
                onClick={handleClose}
              >
                Cancelar
              </button>
            </>
          )}

          {phase === "confirming" && selected && (
            <div className={styles.confirmBox}>
              <div className={styles.confirmTitle}>
                Confirmar asignacion en ADO
              </div>
              <div className={styles.confirmDetail}>
                <strong>Ticket:</strong> ADO-{ticket.ado_id} — {ticket.title}
                <br />
                <strong>Asignar a:</strong> {selected.display_name} ({selected.ado_unique_name})
                <br />
                <strong>Score:</strong> {(selected.score * 100).toFixed(0)}%
                <br />
                <strong>Razon:</strong> {selected.reason}
              </div>
              {dryRunResult && (
                <div style={{ fontSize: 11, color: "#374151", marginBottom: 10 }}>
                  <strong>Se ejecutara en ADO:</strong>
                  {dryRunResult.actions.map((a) => (
                    <div key={a.action} style={{ fontFamily: "monospace", marginTop: 2 }}>
                      {a.would_call}
                    </div>
                  ))}
                </div>
              )}
              {error && <div className={styles.error}>{error}</div>}
              <div className={styles.confirmActions}>
                <button className={styles.btnPrimary} onClick={handleConfirm}>
                  Confirmar asignacion
                </button>
                <button
                  className={styles.btnSecondary}
                  onClick={() => { setPhase("recommendations"); setSelected(null); }}
                >
                  Volver a candidatos
                </button>
                <button className={styles.btnDanger} onClick={handleClose}>
                  Cancelar
                </button>
              </div>
            </div>
          )}

          {phase === "applying" && (
            <div className={styles.loading}>
              Aplicando asignacion en ADO...
            </div>
          )}

          {phase === "done" && (
            <div className={styles.success}>
              Asignacion aplicada correctamente en ADO. El ticket fue sincronizado.
              <button
                className={styles.btnSecondary}
                style={{ marginLeft: 10 }}
                onClick={handleClose}
              >
                Cerrar
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AssignmentRecommendationPanel;

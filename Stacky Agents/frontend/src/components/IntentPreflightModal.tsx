/**
 * Plan 41 F4 — Modal de Pre-vuelo de Intención.
 *
 * Muestra lo que el BusinessAgent interpretó del brief:
 * - Objetivo (resumen)
 * - Deliverables (lista)
 * - Supuestos (con badges de impacto y alertas si high)
 * - Preguntas abiertas (resaltadas si hay)
 * - Áreas que toca
 * - Badge de confianza (% con colores)
 *
 * El operador puede:
 * - Arrancar así (onApprove sin correcciones)
 * - Corregir en textarea y arrancar (onApprove con corrections)
 * - Cancelar (onCancel)
 */

import React, { useState } from "react";
import type { IntentBriefDTO } from "../api/endpoints";
import styles from "./IntentPreflightModal.module.css";

interface IntentPreflightModalProps {
  intent: IntentBriefDTO;
  onApprove: (corrections?: string) => void;
  onCancel: () => void;
}

function confidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.8) return styles.confidenceHigh;
  if (confidence >= 0.5) return styles.confidenceAmber;
  return styles.confidenceLow;
}

export default function IntentPreflightModal({
  intent,
  onApprove,
  onCancel,
}: IntentPreflightModalProps) {
  const [corrections, setCorrections] = useState("");
  const highAssumptions = intent.assumptions.filter((a) => a.impact === "high");
  const hasOpenQuestions = intent.open_questions && intent.open_questions.length > 0;

  function handleApproveAsIs() {
    onApprove(undefined);
  }

  function handleApproveWithCorrections() {
    if (corrections.trim()) {
      onApprove(corrections.trim());
    }
  }

  return (
    <div className={styles.backdrop} onClick={(e) => {
      if (e.target === e.currentTarget) onCancel();
    }}>
      <div className={styles.modal} role="dialog" aria-modal="true">
        <header className={styles.header}>
          <h2 className={styles.title}>Esto es lo que entendí. ¿Arranco así?</h2>
          <div className={`${styles.confidenceBadge} ${confidenceBadgeClass(intent.confidence)}`}>
            {Math.round(intent.confidence * 100)}%
          </div>
        </header>

        <div className={styles.body}>
          {/* Objetivo */}
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Objetivo</h3>
            <p className={styles.objective}>{intent.objective}</p>
          </section>

          {/* Deliverables */}
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Voy a producir</h3>
            <ul className={styles.deliverablesList}>
              {intent.deliverables.map((d, idx) => (
                <li key={idx}>{d}</li>
              ))}
            </ul>
          </section>

          {/* Supuestos */}
          {intent.assumptions && intent.assumptions.length > 0 && (
            <section className={styles.section}>
              <h3 className={styles.sectionTitle}>
                Supuestos
                {highAssumptions.length > 0 && (
                  <span className={styles.alertBadge}>⚠ {highAssumptions.length} de alto impacto</span>
                )}
              </h3>
              <ul className={styles.assumptionsList}>
                {intent.assumptions.map((a, idx) => (
                  <li
                    key={idx}
                    className={a.impact === "high" ? styles.assumptionHigh : ""}
                  >
                    <span className={styles.assumptionText}>{a.text}</span>
                    <span className={`${styles.impactBadge} ${styles[`impact${a.impact}`]}`}>
                      {a.impact === "high" ? "🚨" : a.impact === "medium" ? "⚡" : "ℹ"}{" "}
                      {a.impact}
                    </span>
                    {a.needs_confirmation && (
                      <span className={styles.confirmBadge}>Requiere confirmación</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Preguntas abiertas */}
          {hasOpenQuestions && (
            <section className={styles.section}>
              <h3 className={styles.sectionTitle}>
                Preguntas antes de arrancar
              </h3>
              <div className={styles.openQuestionsBanner}>
                <ul className={styles.questionsList}>
                  {intent.open_questions.map((q, idx) => (
                    <li key={idx}>{q}</li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {/* Áreas */}
          {intent.areas && intent.areas.length > 0 && (
            <section className={styles.section}>
              <h3 className={styles.sectionTitle}>Tocaría</h3>
              <div className={styles.areasTags}>
                {intent.areas.map((area, idx) => (
                  <span key={idx} className={styles.areaTag}>{area}</span>
                ))}
              </div>
            </section>
          )}

          {/* Textarea para correcciones */}
          <section className={styles.section}>
            <label className={styles.label}>
              Corregir o aclarar (opcional)
              <textarea
                className={styles.correctionsTextarea}
                rows={4}
                value={corrections}
                onChange={(e) => setCorrections(e.target.value)}
                placeholder="Si algo no está bien, escribilo acá. Será tenido en cuenta para regenerar la intención."
              />
            </label>
          </section>
        </div>

        <footer className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onCancel}>
            Cancelar
          </button>
          <button
            className={styles.primaryBtn}
            onClick={handleApproveAsIs}
            type="button"
          >
            Arrancar así
          </button>
          <button
            className={styles.secondaryBtn}
            onClick={handleApproveWithCorrections}
            disabled={!corrections.trim()}
            title={!corrections.trim() ? "Escribí una corrección primero" : undefined}
            type="button"
          >
            Corregir y arrancar
          </button>
        </footer>
      </div>
    </div>
  );
}

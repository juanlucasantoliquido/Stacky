/**
 * Plan 267 F6 — Tarjeta de propuesta de acción DevOps.
 *
 * Contrato visual OBLIGATORIO, en este orden vertical:
 *   1. Qué acción (label + summary)      5. Parámetros (nombre/valor/origen)
 *   2. Sobre qué entorno (chip)          6. Preguntas abiertas
 *   3. Cuál es el impacto (chip)         7. Alternativas (si ambiguo)
 *   4. Qué va a pasar                    8. Acciones   9. Recibo
 *
 * CERO estilos en línea y CERO diálogos nativos del navegador: uiDebtRatchet
 * congela los dos por archivo y un archivo NUEVO tiene presupuesto CERO. Todo el
 * aspecto va por CSS modules con tokens del tema. Toda la lógica decidible vive
 * en devopsActionConsoleModel.ts, que sí es testeable (no hay RTL ni jsdom).
 * OJO: esta prosa no puede citar el literal del atributo de estilo en línea ni
 * el nombre de los diálogos nativos, porque el ratchet los cuenta también en los
 * comentarios y el archivo se auto-caza.
 */
import React from 'react';
import type { DevOpsActionReceipt } from '../../services/devopsActionRunner';
import styles from './DevOpsActionConsole.module.css';
import type { ChipTone, ProposalView } from './devopsActionConsoleModel';
import {
  blockedExplanation,
  headerChips,
  isRunDisabled,
  primaryActionLabel,
  receiptLine,
  verEnElPanelPath,
} from './devopsActionConsoleModel';

const TONE_CLASS: Record<ChipTone, string> = {
  ok: styles.toneOk,
  warn: styles.toneWarn,
  bad: styles.toneBad,
  faint: styles.toneFaint,
};

export interface DevOpsActionProposalCardProps {
  proposal: ProposalView;
  receipt?: DevOpsActionReceipt | null;
  busy?: boolean;
  onParamChange: (name: string, value: string) => void;
  onRun: () => void;
  onNavigate: (path: string) => void;
  onPickAlternative: (actionId: string) => void;
}

export const DevOpsActionProposalCard: React.FC<DevOpsActionProposalCardProps> = ({
  proposal,
  receipt,
  busy = false,
  onParamChange,
  onRun,
  onNavigate,
  onPickAlternative,
}) => {
  const chips = headerChips(proposal);
  const bloqueo = blockedExplanation(proposal);
  const runDisabled = isRunDisabled(proposal) || busy;

  return (
    <section className={styles.card} aria-label="Propuesta de acción DevOps">
      {/* 1 — qué acción */}
      <h4 className={styles.cardTitle}>{proposal.label}</h4>
      <p className={styles.cardSummary}>{proposal.summary}</p>

      {/* 2 y 3 — entorno e impacto */}
      <div className={styles.chips}>
        {chips.map((c, i) => (
          <span key={`${c.text}-${i}`} className={`${styles.chip} ${TONE_CLASS[c.tone]}`}>
            {c.text}
          </span>
        ))}
      </div>

      {/* 4 — qué va a pasar (textual, del backend) */}
      <p className={styles.whatWillHappen}>{proposal.whatWillHappen}</p>

      {/* 5 — parámetros */}
      <table className={styles.paramsTable}>
        <thead>
          <tr>
            <th scope="col">Dato</th>
            <th scope="col">Valor</th>
            <th scope="col">Origen</th>
          </tr>
        </thead>
        <tbody>
          {proposal.params.map((p) => (
            <tr key={p.name}>
              <td>{p.label || p.name}</td>
              <td>
                {p.source === 'missing' ? (
                  <input
                    className={styles.paramInput}
                    aria-label={p.label || p.name}
                    value={p.value}
                    onChange={(e) => onParamChange(p.name, e.target.value)}
                  />
                ) : (
                  p.value
                )}
              </td>
              <td className={p.source === 'missing' ? styles.sourceMissing : undefined}>
                {p.source === 'operator'
                  ? 'lo pusiste vos'
                  : p.source === 'default'
                    ? 'valor por omisión'
                    : 'falta'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 6 — preguntas abiertas */}
      {proposal.openQuestions.length > 0 && (
        <ul className={styles.questions}>
          {proposal.openQuestions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      )}

      {/* 7 — alternativas, sólo si hubo ambigüedad */}
      {proposal.blockedReason === 'ambiguous' && proposal.alternatives.length > 0 && (
        <div className={styles.actionsRow}>
          {proposal.alternatives.map((alt) => (
            <button
              key={alt}
              type="button"
              className={styles.altButton}
              onClick={() => onPickAlternative(alt)}
            >
              {alt}
            </button>
          ))}
        </div>
      )}

      {bloqueo && <p className={styles.blocked}>{bloqueo}</p>}

      {/* 8 — acciones */}
      <div className={styles.actionsRow}>
        <button
          type="button"
          className={proposal.impact === 'high' ? styles.dangerButton : styles.secondaryButton}
          disabled={runDisabled}
          onClick={onRun}
        >
          {primaryActionLabel(proposal)}
        </button>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => onNavigate(verEnElPanelPath(proposal))}
        >
          Ver en el panel
        </button>
      </div>

      {/* 9 — recibo */}
      {receipt && <p className={styles.receipt}>{receiptLine(receipt)}</p>}
    </section>
  );
};

export default DevOpsActionProposalCard;

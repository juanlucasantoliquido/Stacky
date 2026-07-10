/**
 * RemediationCard.tsx — Plan 116 F3.
 *
 * Tarjeta presentacional pura: muestra "qué pasó + cómo arreglarlo" para un
 * DiagResult accionable (fail|warn). Si no hay remediación, no renderiza nada.
 */
import { useState } from 'react';
import type { ConnectionDiagResult } from '../../api/endpoints';
import styles from './devops.module.css';

interface Props {
  result: ConnectionDiagResult;
  onRetry?: () => void;
  onGotoSection?: (sectionId: string) => void;
}

export function RemediationCard({ result, onRetry, onGotoSection }: Props) {
  const [copied, setCopied] = useState(false);
  const rem = result.remediation;
  if (!rem) return null;

  const icon = result.status === 'fail' ? '✖' : '⚠';
  const action = rem.action;

  const handleCopy = () => {
    void navigator.clipboard?.writeText(action.command ?? '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={styles.remediationCard}>
      <div className={styles.remediationCardTitle}>
        {icon} {rem.title} — {result.target_label}
      </div>
      <div className={styles.remediationCause}>
        Qué pasó: {rem.cause}
        {result.detail && (
          <details>
            <summary>Detalle técnico</summary>
            <code>{result.detail}</code>
          </details>
        )}
      </div>
      <ol className={styles.remediationSteps}>
        {rem.steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
      <div className={styles.remediationActions}>
        {action.kind === 'retry' && (
          <button type="button" onClick={() => onRetry?.()}>Reintentar</button>
        )}
        {action.kind === 'copy_command' && (
          <button type="button" onClick={handleCopy}>
            {copied ? 'Copiado ✓' : 'Copiar comando'}
          </button>
        )}
        {action.kind === 'open_url' && (
          <button type="button" onClick={() => window.open(action.url, '_blank', 'noopener')}>
            Abrir página
          </button>
        )}
        {action.kind === 'goto_section' && (
          <button type="button" onClick={() => onGotoSection?.(action.section_id ?? '')}>
            Ir a la sección
          </button>
        )}
      </div>
    </div>
  );
}

export default RemediationCard;

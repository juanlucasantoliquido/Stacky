/**
 * FlagGateBanner (Plan 87 F4/F5 - C14)
 * Banner reusable que muestra un aviso cuando una flag está OFF
 * y ofrece activarla con un solo click.
 *
 * Reusa la API existente HarnessFlags.update (endpoints.ts:858-874)
 *
 * HITL: nada se activa sin click explícito del operador.
 */
import React, { useState } from 'react';
import { HarnessFlags } from '../../api/endpoints';
import { classifyFlagUpdateOutcome } from '../../utils/flagUpdateOutcome';
import styles from './devops.module.css';

export interface FlagGateBannerProps {
  flagKey: string;
  flagLabel: string;
  message: string;
  onEnabled: () => void;
}

export const FlagGateBanner: React.FC<FlagGateBannerProps> = ({
  flagKey,
  flagLabel,
  message,
  onEnabled,
}) => {
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const handleActivate = async () => {
    setActivating(true);
    setError(null);
    setNotice(null);
    try {
      const result = await HarnessFlags.update({ [flagKey]: true });
      const outcome = classifyFlagUpdateOutcome(result);
      if (outcome.kind === 'error') {
        setError(outcome.message);
        return; // sin onEnabled: la flag NO quedó activa
      }
      if (outcome.kind === 'warning') {
        setNotice('Flag activada. Requiere reiniciar el backend para aplicar.');
      }
      onEnabled();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red al activar';
      setError(msg);
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className={`${styles.alertWarning} ${styles.flagGateBanner__root}`}>
      <div className={styles.flagGateBanner__msg}>
        <strong>{flagLabel}</strong>: {message}
      </div>
      <div>
        <button
          onClick={handleActivate}
          disabled={activating}
          className={[styles.btnSuccess, styles.flagGateBanner__btn,
                      activating ? styles.flagGateBanner__btnBusy : ''].filter(Boolean).join(' ')}
        >
          {activating ? 'Activando...' : 'Activar ahora'}
        </button>
      </div>
      {error && (
        <div className={`${styles.textDanger} ${styles.flagGateBanner__error}`}>
          {error}
        </div>
      )}
      {notice && (
        <div className={styles.flagGateBanner__notice} role="status">
          {notice}
        </div>
      )}
    </div>
  );
};

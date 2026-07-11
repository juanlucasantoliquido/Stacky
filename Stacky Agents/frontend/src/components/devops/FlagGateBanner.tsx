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

  const handleActivate = async () => {
    setActivating(true);
    setError(null);
    try {
      const result = await HarnessFlags.update({ [flagKey]: true });
      if (result.ok) {
        onEnabled();
      } else {
        setError(result.error || 'Error al activar la flag');
      }
      // Si hay restart_required, mostramos aviso (no aplica a flags DevOps, pero por robustez)
      if (result.restart_required_keys && result.restart_required_keys.length > 0) {
        setError('El cambio quedó guardado pero requiere reiniciar el backend');
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red al activar';
      setError(msg);
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className={styles.alertWarning} style={{ marginBottom: '16px' }}>
      <div style={{ marginBottom: '8px' }}>
        <strong>{flagLabel}</strong>: {message}
      </div>
      <div>
        <button
          onClick={handleActivate}
          disabled={activating}
          className={styles.btnSuccess}
          style={{ padding: '6px 12px', opacity: activating ? 0.6 : 1 }}
        >
          {activating ? 'Activando...' : 'Activar ahora'}
        </button>
      </div>
      {error && (
        <div className={styles.textDanger} style={{ marginTop: '8px', fontSize: '0.9em' }}>
          {error}
        </div>
      )}
    </div>
  );
};

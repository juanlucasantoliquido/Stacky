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
    <div
      style={{
        padding: '12px 16px',
        backgroundColor: '#fff3cd',
        border: '1px solid #ffc107',
        borderRadius: '4px',
        marginBottom: '16px',
      }}
    >
      <div style={{ marginBottom: '8px', color: '#856404' }}>
        <strong>{flagLabel}</strong>: {message}
      </div>
      <div>
        <button
          onClick={handleActivate}
          disabled={activating}
          style={{
            padding: '6px 12px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '3px',
            cursor: activating ? 'not-allowed' : 'pointer',
            opacity: activating ? 0.6 : 1,
          }}
        >
          {activating ? 'Activando...' : 'Activar ahora'}
        </button>
      </div>
      {error && (
        <div style={{ marginTop: '8px', color: '#721c24', fontSize: '0.9em' }}>
          {error}
        </div>
      )}
    </div>
  );
};

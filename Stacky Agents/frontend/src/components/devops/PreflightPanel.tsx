/**
 * PreflightPanel (Plan 93 F4)
 * Semáforo de preflight "¿Va a funcionar?" — SOLO-LECTURA, informativo, NUNCA
 * bloquea commit/trigger (HITL §3.3: el operador decide).
 */
import React, { useState } from 'react';
import { DevOps } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { FlagGateBanner } from './FlagGateBanner';
import {
  overallStatus,
  sortBySeverity,
  summaryLine,
  type PreflightCheck,
  type PreflightResult,
  type PreflightStatus,
} from '../../devops/preflightModel';
import styles from './devops.module.css';

export interface PreflightPanelProps {
  ctx: DevOpsSectionContext;
  spec: object;
  project: string;
  onResult?: (r: PreflightResult) => void;
}

const STATUS_LABEL: Record<PreflightStatus, string> = {
  ok: '✔',
  warn: '⚠',
  fail: '✖',
  unavailable: '–',
};

const STATUS_CLASS: Record<PreflightStatus, string> = {
  ok: styles.textSuccess,
  warn: styles.textWarn,
  fail: styles.textDanger,
  unavailable: styles.textMuted,
};

export const PreflightPanel: React.FC<PreflightPanelProps> = ({ ctx, spec, project, onResult }) => {
  const [result, setResult] = useState<PreflightResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (ctx.health.preflight_enabled !== true) {
    return (
      <FlagGateBanner
        flagKey="STACKY_DEVOPS_PREFLIGHT_ENABLED"
        flagLabel="Preflight de pipelines"
        message="El botón '¿Va a funcionar?' necesita la flag STACKY_DEVOPS_PREFLIGHT_ENABLED (Configuración → Arnés, categoría DevOps)."
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  const handleCheck = async () => {
    if (!project) {
      setError('Seleccioná un proyecto activo primero.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await DevOps.preflightCheck(project, spec, 'auto');
      setResult(r);
      onResult?.(r);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red al chequear el pipeline';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const sortedChecks: PreflightCheck[] = result ? sortBySeverity(result.checks) : [];
  const overall = result ? overallStatus(result.checks) : null;

  return (
    <div className={styles.panelMuted} style={{ marginTop: '16px' }}>
      <h3 style={{ marginTop: 0 }}>¿Va a funcionar?</h3>
      <p className={styles.textMuted} style={{ marginTop: 0, fontSize: '0.9em' }}>
        Chequeo solo-lectura: no commitea ni dispara nada. Vos decidís si seguís, aunque haya avisos.
      </p>

      <button
        onClick={() => void handleCheck()}
        disabled={loading || !project}
        className={styles.btnPrimary}
        style={{ padding: '8px 16px' }}
      >
        {loading ? 'Chequeando…' : '¿Va a funcionar?'}
      </button>

      {overall && (
        <div style={{ marginTop: '12px' }}>
          <strong className={STATUS_CLASS[overall]}>
            {STATUS_LABEL[overall]} {summaryLine(result!.checks)}
          </strong>
        </div>
      )}

      {sortedChecks.length > 0 && (
        <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {sortedChecks.map((check) => (
            <div key={check.id} className={styles.panel} style={{ padding: '8px' }}>
              <div className={STATUS_CLASS[check.status]}>
                <strong>{STATUS_LABEL[check.status]} {check.title}</strong>
              </div>
              {check.detail && (
                <div style={{ fontSize: '0.85em', marginTop: '4px' }}>{check.detail}</div>
              )}
              {check.fix_hint && (
                <div className={styles.textMuted} style={{ fontSize: '0.85em', marginTop: '4px' }}>
                  Sugerencia: {check.fix_hint}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className={styles.alertError} style={{ marginTop: '12px' }}>
          {error}
        </div>
      )}
    </div>
  );
};

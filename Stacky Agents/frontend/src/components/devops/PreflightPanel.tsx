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
    <div className={`${styles.panelMuted} ${styles.preflight__root}`}>
      <h3 className={styles.preflight__title}>¿Va a funcionar?</h3>
      <p className={`${styles.textMuted} ${styles.preflight__desc}`}>
        Chequeo solo-lectura: no commitea ni dispara nada. Vos decidís si seguís, aunque haya avisos.
      </p>

      <button
        onClick={() => void handleCheck()}
        disabled={loading || !project}
        className={`${styles.btnPrimary} ${styles.preflight__btn}`}
      >
        {loading ? 'Chequeando…' : '¿Va a funcionar?'}
      </button>

      {overall && (
        <div className={styles.preflight__mt}>
          <strong className={STATUS_CLASS[overall]}>
            {STATUS_LABEL[overall]} {summaryLine(result!.checks)}
          </strong>
        </div>
      )}

      {sortedChecks.length > 0 && (
        <div className={styles.preflight__list}>
          {sortedChecks.map((check) => (
            <div key={check.id} className={`${styles.panel} ${styles.preflight__item}`}>
              <div className={STATUS_CLASS[check.status]}>
                <strong>{STATUS_LABEL[check.status]} {check.title}</strong>
              </div>
              {check.detail && (
                <div className={styles.preflight__detail}>{check.detail}</div>
              )}
              {check.fix_hint && (
                <div className={`${styles.textMuted} ${styles.preflight__detail}`}>
                  Sugerencia: {check.fix_hint}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className={`${styles.alertError} ${styles.preflight__mt}`}>
          {error}
        </div>
      )}
    </div>
  );
};

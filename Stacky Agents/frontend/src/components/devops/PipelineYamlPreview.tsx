/**
 * PipelineYamlPreview (Plan 87 F5)
 * Preview vivo de YAML ADO y GitLab con FlagGateBanner (C14) y auto-refresh (C17)
 */
import React, { useState, useEffect, useRef } from 'react';
import { PipelineGenerator, PipelineProfiler } from '../../api/endpoints';
// Plan 247 F5 — ficha del perfil debajo del preview ADO (aditivo: si falla, no se renderiza).
import { PipelineProfileCard } from './PipelineProfileCard';
import type { PipelineProfileDto } from '../../devops/pipelineProfileModel';
import { FlagGateBanner } from './FlagGateBanner';
import { toSpecDict, type PipelineSpecDraft } from '../../devops/specBuilder';
import { createPreviewFetcher, type PreviewFetcher } from '../../devops/previewFetcher'; // Plan 99
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import styles from './devops.module.css';

export interface PipelineYamlPreviewProps {
  spec: PipelineSpecDraft;
  ctx: DevOpsSectionContext;
  localErrors: string[];
  /** Plan 186 F5/C7 — línea 1-based a resaltar. undefined = render actual intacto. */
  highlightLine?: number;
}

export const PipelineYamlPreview: React.FC<PipelineYamlPreviewProps> = ({ spec, ctx, localErrors, highlightLine }) => {
  const highlightRef = useRef<HTMLDivElement | null>(null);

  // C7 — cuando highlightLine está definido, render por líneas para resaltar una;
  // undefined ⇒ render EXACTAMENTE igual que hoy (string único dentro del <pre>).
  const renderYaml = (text: string): React.ReactNode => {
    if (highlightLine === undefined) return text;
    return text.split('\n').map((ln, i) => {
      const isHi = i === highlightLine - 1;
      return (
        <div
          key={i}
          ref={isHi ? highlightRef : undefined}
          className={isHi ? styles.lineHighlight : styles.yamlLine}
        >
          {ln.length ? ln : ' '}
        </div>
      );
    });
  };

  useEffect(() => {
    if (highlightLine !== undefined && highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: 'center' });
    }
  }, [highlightLine]);

  const [preview, setPreview] = useState<{ ado: string; gitlab: string } | null>(null);
  const [previewErrors, setPreviewErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [loading, setLoading] = useState(false);
  // Plan 247 F5
  const [profile, setProfile] = useState<PipelineProfileDto | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Plan 99 F2 — fetcher con cache + anti-stale; una instancia por montaje
  // (se descarta al desmontar, así que nunca sirve YAML rancio entre sesiones).
  const fetcherRef = useRef<PreviewFetcher | null>(null);
  if (fetcherRef.current === null) {
    fetcherRef.current = createPreviewFetcher(
      (s, signal) => PipelineGenerator.preview(s, signal),
    );
  }

  // Refrescar preview manual o auto
  const refreshPreview = async (force = false) => {
    if (localErrors.length > 0) return; // No preview si hay errores locales
    if (force) fetcherRef.current!.invalidate();
    setLoading(true);
    // Plan 99 — los errores NO se blanquean al iniciar (eso causaba el parpadeo):
    // se limpian recién en el desenlace exitoso, más abajo.
    const outcome = await fetcherRef.current!.request(toSpecDict(spec));
    // Hay un pedido más nuevo en vuelo: NO tocar estado, ni siquiera el loading
    // (lo apaga el pedido que sí manda).
    if (outcome.kind === 'stale') return;
    setLoading(false);
    if (outcome.kind === 'error') {
      setPreviewErrors(outcome.errors); // el preview viejo QUEDA visible (SWR)
      return;
    }
    const result = outcome.data;
    setPreview(result);
    setPreviewErrors([]);
    // Plan 247 F5 — el perfil es aditivo: su fallo NUNCA degrada el preview. NO BORRAR.
    try {
      setProfile(await PipelineProfiler.profile({ yaml_text: result.ado }));
      setProfileError(null);
    } catch (pe: unknown) {
      setProfile(null);
      setProfileError(pe instanceof Error ? pe.message : 'perfil no disponible');
    }
  };

  // C17 - auto-refresh con debounce de 800ms tras el último cambio del spec
  // (solo si generator_enabled y sin errores locales; el botón manual sigue
  // siempre disponible más abajo).
  useEffect(() => {
    if (!ctx.health.generator_enabled || localErrors.length > 0) return;
    const timeoutId = setTimeout(() => {
      void refreshPreview();
    }, 800);
    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, ctx.health.generator_enabled, localErrors.length]);

  // C14 - FlagGateBanner si generator_enabled=false
  if (!ctx.health.generator_enabled) {
    return (
      <FlagGateBanner
        flagKey="STACKY_PIPELINE_GENERATOR_ENABLED"
        flagLabel="Generador de pipelines"
        message="El preview y el commit necesitan el Generador de pipelines (flag STACKY_PIPELINE_GENERATOR_ENABLED, categoría 'Épicas, briefs y publicación en ADO')."
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  return (
    <div className={styles.panelMuted}>
      <div className={styles.previewHeader}>
        <h3 style={{ margin: 0 }}>
          Preview YAML{' '}
          {/* Plan 99 — SWR honesto: mientras recalcula, el YAML anterior sigue
              visible y atenuado en vez de desaparecer. */}
          {loading && <span className={styles.recalcBadge}>Recalculando…</span>}
        </h3>
        <button
          onClick={() => void refreshPreview(true)}
          disabled={loading || localErrors.length > 0}
          title={localErrors.length > 0 ? 'Resolvé los avisos primero' : undefined}
          style={{ padding: '6px 12px', fontSize: '12px' }}
        >
          {loading ? 'Actualizando...' : 'Actualizar preview'}
        </button>
      </div>

      {/* C12 - errores locales visibles */}
      {localErrors.length > 0 && (
        <div className={styles.alertWarning} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px' }}>
          <strong>Antes del preview:</strong>
          <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
            {localErrors.map((err, i) => (
              <li key={i} style={{ fontSize: '13px' }}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Errores del backend */}
      {previewErrors.length > 0 && (
        <div className={styles.alertError} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px' }}>
          <strong>Errores de validación:</strong>
          <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
            {previewErrors.map((err, i) => (
              <li key={i} style={{ fontSize: '13px' }}>
                {err.field ? `${err.field}: ` : ''}{err.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Preview lado a lado */}
      {preview && (
        <div style={{ display: 'flex', gap: '16px' }}>
          <div style={{ flex: 1 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '14px' }}>Azure DevOps</h4>
            <pre className={`${styles.yamlPre} ${loading ? styles.yamlPreStale : ''}`}>
              {renderYaml(preview.ado)}
            </pre>
          </div>
          <div style={{ flex: 1 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '14px' }}>GitLab CI</h4>
            <pre className={`${styles.yamlPre} ${loading ? styles.yamlPreStale : ''}`}>
              {renderYaml(preview.gitlab)}
            </pre>
          </div>
        </div>
      )}

      {/* Plan 247 F5 — ficha del perfil (qué hace la pipeline y qué NO hace) */}
      {preview && (
        <PipelineProfileCard profile={profile} loading={loading} error={profileError} />
      )}
    </div>
  );
};

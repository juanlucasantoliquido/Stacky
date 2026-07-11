/**
 * PrReviewerSection (Plan 110 F7)
 *
 * Sección "Revisor de PRs" del panel DevOps. Lista las PRs del tracker
 * activo y permite:
 *  - Revisar con Claude Haiku (solo-lectura) — EXTERNO: exige preview del payload
 *    saneado + checkbox "confirmo el envío" antes de mandar nada a Copilot/GitHub (C1).
 *  - Revisar SOLO con el modelo local (nada sale de tu máquina) — camino privado,
 *    recibe el diff completo, SIN checkbox de envío externo (v2.1).
 *  - Ejecutar la acción recomendada con un botón (HITL). Merge = checkbox literal.
 *
 * El gate de flag-off lo hace el SHELL (DevOpsPage) por healthKey/gateFlagKey.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWorkbench } from '../../store/workbench';
import {
  PrReview,
  type PrSummary,
  type PrHaikuReview,
  type PrReviewDetail,
} from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import styles from './PrReviewerSection.module.css';

export interface PrReviewerSectionProps {
  ctx: DevOpsSectionContext;
}

const PRIVACY_NOTICE =
  'El contenido del cambio (diff) se envía al modelo. Con el modelo local queda en tu máquina; ' +
  'con Haiku viaja al servicio de Copilot/GitHub. Los secretos evidentes se ocultan, pero revisá ' +
  'que no haya datos sensibles.';

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

type PrStateFilter = 'open' | 'merged' | 'closed' | 'all';

const STATE_FILTERS: { value: PrStateFilter; label: string }[] = [
  { value: 'open', label: 'Abiertas' },
  { value: 'merged', label: 'Mergeadas' },
  { value: 'closed', label: 'Cerradas' },
  { value: 'all', label: 'Todas' },
];

const STATE_BADGE: Record<string, { label: string; cls: string }> = {
  open: { label: 'Abierta', cls: 'stOpen' },
  merged: { label: 'Mergeada', cls: 'stMerged' },
  closed: { label: 'Cerrada', cls: 'stClosed' },
};

const PIPELINE_BADGE: Record<string, { label: string; cls: string }> = {
  success: { label: 'Pipeline OK', cls: 'pipeSuccess' },
  failed: { label: 'Pipeline falló', cls: 'pipeFailed' },
  running: { label: 'Corriendo', cls: 'pipeRunning' },
  pending: { label: 'Pendiente', cls: 'pipePending' },
  created: { label: 'Creado', cls: 'pipePending' },
  canceled: { label: 'Cancelado', cls: 'pipeMuted' },
};

const SEVERITY_CLASS: Record<string, string> = {
  info: 'sevInfo',
  warning: 'sevWarning',
  critical: 'sevCritical',
};

export const PrReviewerSection: React.FC<PrReviewerSectionProps> = ({ ctx }) => {
  void ctx;
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  const [stateFilter, setStateFilter] = useState<PrStateFilter>('open');
  const [selected, setSelected] = useState<PrSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Camino Haiku (externo)
  const [detail, setDetail] = useState<PrReviewDetail | null>(null);
  const [confirmExternalSend, setConfirmExternalSend] = useState(false);
  const [haikuReview, setHaikuReview] = useState<PrHaikuReview | null>(null);
  const [haikuBusy, setHaikuBusy] = useState(false);

  // Camino local (privado)
  const [question, setQuestion] = useState('');
  const [localAnswer, setLocalAnswer] = useState<string | null>(null);
  const [localBusy, setLocalBusy] = useState(false);

  // Ejecución de acción (HITL)
  const [commentBody, setCommentBody] = useState('');
  const [confirmMerge, setConfirmMerge] = useState(false);
  const [actions, setActions] = useState<string[]>([]);
  const [models, setModels] = useState<{ id: string; name: string; is_haiku: boolean }[] | null>(null);

  const listQuery = useQuery({
    queryKey: ['pr-review-list', activeProject, stateFilter],
    queryFn: () => PrReview.list(activeProject, stateFilter),
    enabled: !!activeProject,
    retry: false,
  });

  const prs = listQuery.data?.merge_requests ?? [];

  const resetForPr = (pr: PrSummary) => {
    setSelected(pr);
    setError(null);
    setDetail(null);
    setConfirmExternalSend(false);
    setHaikuReview(null);
    setLocalAnswer(null);
    setQuestion('');
    setCommentBody('');
    setConfirmMerge(false);
    PrReview.actions(activeProject)
      .then((r) => setActions(r.actions))
      .catch(() => setActions([]));
  };

  const loadPreview = async () => {
    if (!selected) return;
    setError(null);
    try {
      const d = await PrReview.detail(activeProject, selected.id);
      setDetail(d);
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const runHaiku = async () => {
    if (!selected || !confirmExternalSend) return;
    setHaikuBusy(true);
    setError(null);
    try {
      const r = await PrReview.reviewHaiku(activeProject, selected.id);
      setHaikuReview(r.review);
      setCommentBody(r.review.recommended_action?.label ?? '');
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setHaikuBusy(false);
    }
  };

  const loadModels = async () => {
    setError(null);
    try {
      const r = await PrReview.models();
      setModels(r.models);
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const execAction = async (action: string) => {
    if (!selected) return;
    setError(null);
    try {
      await PrReview.execute({
        project: activeProject,
        mr_id: selected.id,
        action,
        body: commentBody || undefined,
        confirm: true,
        confirm_merge: action === 'merge' ? confirmMerge : undefined,
      });
      listQuery.refetch();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const recommended = haikuReview?.recommended_action?.type ?? 'none';

  if (!activeProject) {
    return <div className={styles.notice}>Elegí un proyecto activo para revisar sus PRs.</div>;
  }

  const renderStateBadge = (state: string) => {
    const b = STATE_BADGE[state] ?? STATE_BADGE.open;
    return <span className={`${styles.badge} ${styles[b.cls]}`}>{b.label}</span>;
  };

  const renderPipelineBadge = (status: string) => {
    const b = PIPELINE_BADGE[status];
    if (!b) return <span className={`${styles.badge} ${styles.pipeMuted}`}>—</span>;
    return (
      <span className={`${styles.badge} ${styles[b.cls]}`}>
        <span className={styles.badgeDot} />
        {b.label}
      </span>
    );
  };

  return (
    <div className={styles.wrap}>
      <p className={styles.privacy}>🔒 {PRIVACY_NOTICE}</p>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {listQuery.isError && (
        <div className={styles.errorBanner}>
          <span>No se pudieron cargar las PRs: {errMsg(listQuery.error)}</span>
          <button onClick={() => listQuery.refetch()}>Reintentar</button>
        </div>
      )}

      <div className={styles.toolbar}>
        <div className={styles.segmented} role="tablist" aria-label="Filtro de estado de PRs">
          {STATE_FILTERS.map((f) => (
            <button
              key={f.value}
              className={stateFilter === f.value ? styles.segActive : undefined}
              aria-pressed={stateFilter === f.value}
              onClick={() => setStateFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        {listQuery.data?.provider && (
          <span className={styles.providerChip}>{listQuery.data.provider}</span>
        )}
        {listQuery.isSuccess && (
          <span className={styles.countChip}>
            {prs.length} PR{prs.length === 1 ? '' : 's'}
          </span>
        )}
        <span className={styles.toolbarSpacer} />
        <button onClick={() => listQuery.refetch()} disabled={listQuery.isFetching}>
          {listQuery.isFetching ? 'Cargando…' : '↻ Actualizar'}
        </button>
        <button onClick={loadModels}>Ver modelos disponibles</button>
      </div>

      {models && (
        <ul className={styles.modelList}>
          {models.map((m) => (
            <li key={m.id} className={m.is_haiku ? styles.haikuModel : undefined}>
              {m.name} <code>{m.id}</code> {m.is_haiku ? '★ Haiku' : ''}
            </li>
          ))}
        </ul>
      )}

      <div className={styles.tableCard}>
        {listQuery.isFetching && !listQuery.data ? (
          <div aria-label="Cargando PRs">
            <div className={styles.skeletonRow} />
            <div className={styles.skeletonRow} />
            <div className={styles.skeletonRow} />
          </div>
        ) : prs.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Sin PRs {STATE_FILTERS.find((f) => f.value === stateFilter)?.label.toLowerCase()}</strong>
            <span>
              {listQuery.isError
                ? 'Corregí la conexión del tracker y reintentá.'
                : 'Cuando haya pedidos de cambios en el tracker van a aparecer acá.'}
            </span>
          </div>
        ) : (
          <table className={styles.prTable}>
            <thead>
              <tr>
                <th>PR</th>
                <th>Ramas</th>
                <th>Estado</th>
                <th>Pipeline</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {prs.map((pr) => (
                <tr key={pr.id} className={selected?.id === pr.id ? styles.rowSelected : undefined}>
                  <td>
                    <div className={styles.prTitleCell}>
                      <a href={pr.web_url} target="_blank" rel="noreferrer">{pr.title}</a>
                      <span className={styles.prMeta}>
                        #{pr.id}
                        {pr.author ? ` · ${pr.author}` : ''}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={styles.branchFlow}>
                      <span className={styles.branchChip} title={pr.source_branch}>{pr.source_branch}</span>
                      <span className={styles.branchArrow}>→</span>
                      <span className={styles.branchChip} title={pr.target_branch}>{pr.target_branch}</span>
                    </span>
                  </td>
                  <td>{renderStateBadge(pr.state)}</td>
                  <td>{renderPipelineBadge(pr.pipeline_status)}</td>
                  <td>
                    <button className={styles.reviewBtn} onClick={() => resetForPr(pr)}>Revisar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className={styles.reviewPanel}>
          <div className={styles.reviewHeader}>
            <h3>
              <span>PR #{selected.id}</span>
              {selected.title}
            </h3>
            <button className={styles.closeBtn} onClick={() => setSelected(null)} aria-label="Cerrar revisión">
              ✕ Cerrar
            </button>
          </div>

          <div className={styles.pathsGrid}>
            {/* ── Camino Haiku (externo) ───────────────────────────── */}
            <section className={styles.haikuBlock}>
              <h4 className={styles.blockTitle}>
                Revisar con Haiku
                <span className={`${styles.blockTag} ${styles.tagCloud}`}>en la nube</span>
              </h4>
              <button onClick={loadPreview}>Ver exactamente qué se envía a Copilot/GitHub</button>
              {detail && (
                <details open className={styles.previewBox}>
                  <summary>Vista previa del contenido que sale de tu máquina (saneado)</summary>
                  <pre>{detail.diff_text || '(sin diff disponible)'}</pre>
                  {detail.diff_truncated && (
                    <em className={styles.truncNote}>El diff fue truncado por tamaño.</em>
                  )}
                </details>
              )}
              <label className={styles.confirmSend}>
                <input
                  type="checkbox"
                  checked={confirmExternalSend}
                  onChange={(e) => setConfirmExternalSend(e.target.checked)}
                />
                Reviso el contenido y confirmo el envío
              </label>
              <button className={styles.reviewBtn} onClick={runHaiku} disabled={!confirmExternalSend || haikuBusy}>
                {haikuBusy ? 'Revisando…' : 'Revisar con Haiku'}
              </button>
            </section>

            {/* ── Camino SOLO local (privado) ──────────────────────── */}
            <section className={styles.localBlock}>
              <h4 className={styles.blockTitle}>
                Revisar solo con modelo local (nada sale de tu máquina)
                <span className={`${styles.blockTag} ${styles.tagLocal}`}>privado</span>
              </h4>
              <p className={styles.localHint}>
                Privado: el contenido no se envía a Copilot/GitHub. Recomendado para repos con datos personales.
              </p>
              <textarea
                placeholder="Pregunta opcional para el modelo local…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button
                className={styles.reviewBtn}
                onClick={async () => {
                  if (!selected) return;
                  setLocalBusy(true);
                  setError(null);
                  try {
                    const r = await PrReview.reviewLocal(activeProject, selected.id, question);
                    setLocalAnswer(r.answer);
                  } catch (e) {
                    setError(errMsg(e));
                  } finally {
                    setLocalBusy(false);
                  }
                }}
                disabled={localBusy}
              >
                {localBusy ? 'Consultando…' : localAnswer ? 'Preguntar de nuevo' : 'Revisar con modelo local'}
              </button>
              {localAnswer && <pre className={styles.localAnswer}>{localAnswer}</pre>}
            </section>
          </div>

          {haikuReview && (
            <div className={styles.reviewResult}>
              <p><strong>Resumen:</strong> {haikuReview.summary}</p>
              <ul>
                {haikuReview.findings.map((f, i) => (
                  <li key={i} className={styles.finding}>
                    <span className={`${styles.sevBadge} ${styles[SEVERITY_CLASS[f.severity] ?? 'sevInfo']}`}>
                      {f.severity}
                    </span>
                    <span>
                      <strong>{f.title}</strong>: {f.detail}
                    </span>
                  </li>
                ))}
              </ul>
              <span className={styles.actionBadge}>
                Acción recomendada: {haikuReview.recommended_action.label} ({recommended})
              </span>

              {/* ── Ejecutar la acción (HITL) ──────────────────────── */}
              <div className={styles.execBox}>
                {recommended === 'none' && (
                  <button disabled title="El revisor no recomienda ninguna acción">Ejecutar</button>
                )}
                {(recommended === 'comment' || recommended === 'request_changes') && (
                  <>
                    <textarea value={commentBody} onChange={(e) => setCommentBody(e.target.value)} />
                    <button onClick={() => execAction(recommended)}>Ejecutar</button>
                  </>
                )}
                {recommended === 'merge' && (
                  <>
                    <label>
                      <input
                        type="checkbox"
                        checked={confirmMerge}
                        onChange={(e) => setConfirmMerge(e.target.checked)}
                      />
                      Confirmo que quiero mergear esta PR a {selected.target_branch}
                    </label>
                    <button onClick={() => execAction('merge')} disabled={!confirmMerge}>Ejecutar</button>
                  </>
                )}
                {recommended === 'close' && (
                  <button onClick={() => execAction('close')}>Ejecutar</button>
                )}
                {recommended === 'approve' && actions.includes('approve') && (
                  <button onClick={() => execAction('approve')}>Ejecutar</button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

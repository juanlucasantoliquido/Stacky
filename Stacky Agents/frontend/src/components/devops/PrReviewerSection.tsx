/**
 * PrReviewerSection (Plan 110 F7)
 *
 * Sección "Revisor de PRs" del panel DevOps. Lista las PRs abiertas del tracker
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

const SEVERITY_COLOR: Record<string, string> = {
  info: '#3b82f6',
  warning: '#d97706',
  critical: '#dc2626',
};

export const PrReviewerSection: React.FC<PrReviewerSectionProps> = ({ ctx }) => {
  void ctx;
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

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
    queryKey: ['pr-review-list', activeProject],
    queryFn: () => PrReview.list(activeProject),
    enabled: !!activeProject,
    retry: false,
  });

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

  const runLocal = async () => {
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

  return (
    <div className={styles.wrap}>
      <p className={styles.privacy}>{PRIVACY_NOTICE}</p>

      {error && <div className={styles.errorBanner}>{error}</div>}

      <div className={styles.toolbar}>
        <button onClick={() => listQuery.refetch()} disabled={listQuery.isFetching}>
          {listQuery.isFetching ? 'Cargando…' : 'Cargar PRs'}
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
          {(listQuery.data?.merge_requests ?? []).map((pr) => (
            <tr key={pr.id}>
              <td>
                <a href={pr.web_url} target="_blank" rel="noreferrer">{pr.title}</a>
              </td>
              <td>{pr.source_branch} → {pr.target_branch}</td>
              <td>{pr.state}</td>
              <td>{pr.pipeline_status}</td>
              <td>
                <button onClick={() => resetForPr(pr)}>Revisar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <div className={styles.reviewPanel}>
          <h3>PR #{selected.id}: {selected.title}</h3>

          {/* ── Camino Haiku (externo) ─────────────────────────────── */}
          <section className={styles.haikuBlock}>
            <h4>Revisar con Haiku (en la nube)</h4>
            <button onClick={loadPreview}>Ver exactamente qué se envía a Copilot/GitHub</button>
            {detail && (
              <details open className={styles.previewBox}>
                <summary>Vista previa del contenido que sale de tu máquina (saneado)</summary>
                <pre>{detail.diff_text || '(sin diff disponible)'}</pre>
                {detail.diff_truncated && <em>El diff fue truncado por tamaño.</em>}
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
            <button onClick={runHaiku} disabled={!confirmExternalSend || haikuBusy}>
              {haikuBusy ? 'Revisando…' : 'Revisar con Haiku'}
            </button>
          </section>

          {haikuReview && (
            <div className={styles.reviewResult}>
              <p><strong>Resumen:</strong> {haikuReview.summary}</p>
              <ul>
                {haikuReview.findings.map((f, i) => (
                  <li key={i} style={{ color: SEVERITY_COLOR[f.severity] ?? '#333' }}>
                    <strong>{f.title}</strong>: {f.detail}
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

          {/* ── Camino SOLO local (privado) ────────────────────────── */}
          <section className={styles.localBlock}>
            <h4>Revisar solo con modelo local (nada sale de tu máquina)</h4>
            <p className={styles.localHint}>
              Privado: el contenido no se envía a Copilot/GitHub. Recomendado para repos con datos personales.
            </p>
            <textarea
              placeholder="Pregunta opcional para el modelo local…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button onClick={runLocal} disabled={localBusy}>
              {localBusy ? 'Consultando…' : localAnswer ? 'Preguntar de nuevo' : 'Revisar solo con modelo local'}
            </button>
            {localAnswer && <pre className={styles.localAnswer}>{localAnswer}</pre>}
          </section>
        </div>
      )}
    </div>
  );
};

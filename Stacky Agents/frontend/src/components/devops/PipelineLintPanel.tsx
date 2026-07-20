/**
 * PipelineLintPanel (Plan 186 F5)
 * Panel de lint determinista dentro del creador de pipelines: findings PLxxx con
 * línea, diff de fixes (informativo, HITL) y explain-plan. Se auto-oculta con la
 * flag OFF (404). Anti-race por contador de secuencia (C6). CERO style inline.
 */
import React, { useEffect, useRef, useState } from 'react';
import { rawPost } from '../../api/client';
import { PipelineGenerator, DevOpsVariables } from '../../api/endpoints';
import { toSpecDict, type PipelineSpecDraft } from '../../devops/specBuilder';
import {
  groupFindings,
  buildDiffLines,
  type LintReport,
  type LintFinding,
  type LintSource,
  type ExecutionPlan,
  type DiffKind,
} from './pipelineLint';
import styles from './PipelineLintPanel.module.css';

export interface PipelineLintPanelProps {
  spec: PipelineSpecDraft;
  project: string;
  onHighlightLine: (line: number | undefined) => void;
  onReport: (report: LintReport | undefined) => void;
}

const sevClass = (sev: LintFinding['severity']): string =>
  sev === 'error' ? styles.sevError : sev === 'warning' ? styles.sevWarn : styles.sevInfo;

const diffClass = (kind: DiffKind): string =>
  kind === 'add' ? styles.diffAdd : kind === 'del' ? styles.diffDel : styles.diffSame;

const diffPrefix = (kind: DiffKind): string => (kind === 'add' ? '+ ' : kind === 'del' ? '- ' : '  ');

export const PipelineLintPanel: React.FC<PipelineLintPanelProps> = ({
  spec,
  project,
  onHighlightLine,
  onReport,
}) => {
  const [source, setSource] = useState<LintSource>('ado');
  const [report, setReport] = useState<LintReport | undefined>(undefined);
  const [currentYaml, setCurrentYaml] = useState<string>('');
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [knownVars, setKnownVars] = useState<string[] | undefined>(undefined);
  const seqRef = useRef(0);

  const specKey = JSON.stringify(toSpecDict(spec));

  // caja fuerte 94: nombres sin valores (una sola vez por proyecto)
  useEffect(() => {
    let cancelled = false;
    if (!project) {
      setKnownVars(undefined);
      return;
    }
    void (async () => {
      try {
        const res = await DevOpsVariables.list(project);
        if (!cancelled) setKnownVars(res.variables.map((v) => v.key));
      } catch {
        if (!cancelled) setKnownVars(undefined);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [project]);

  useEffect(() => {
    let cancelled = false;
    setPlan(null);
    const t = setTimeout(() => {
      void (async () => {
        setLoading(true);
        let yamlText = '';
        try {
          const pv = await PipelineGenerator.preview(toSpecDict(spec));
          yamlText = source === 'ado' ? pv.ado : pv.gitlab;
        } catch {
          yamlText = '';
        }
        if (cancelled) return;
        if (!yamlText.trim()) {
          setReport(undefined);
          onReport(undefined);
          setLoading(false);
          return;
        }
        setCurrentYaml(yamlText);
        const seq = ++seqRef.current;
        const resp = await rawPost<LintReport>('/api/devops/pipeline-lint/validate', {
          source,
          yaml: yamlText,
          known_variables: knownVars,
        });
        if (cancelled || seq !== seqRef.current) return;
        setLoading(false);
        if (resp.status === 404) {
          setHidden(true);
          return;
        }
        if (resp.ok && resp.data) {
          setReport(resp.data);
          onReport(resp.data);
        }
      })();
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, source, (knownVars ?? []).join(',')]);

  const loadPlan = async () => {
    if (!currentYaml.trim()) return;
    const resp = await rawPost<{ plan: ExecutionPlan }>('/api/devops/pipeline-lint/explain', {
      source,
      yaml: currentYaml,
    });
    if (resp.ok && resp.data) setPlan(resp.data.plan);
  };

  if (hidden) return null;

  const grouped = report ? groupFindings(report.findings) : null;
  const ordered: LintFinding[] = grouped
    ? [...grouped.errors, ...grouped.warnings, ...grouped.infos]
    : [];

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>Lint del pipeline</span>
        <div className={styles.tabs}>
          <button
            type="button"
            className={source === 'ado' ? styles.tabActive : styles.tab}
            onClick={() => setSource('ado')}
          >
            Azure DevOps
          </button>
          <button
            type="button"
            className={source === 'gitlab' ? styles.tabActive : styles.tab}
            onClick={() => setSource('gitlab')}
          >
            GitLab
          </button>
        </div>
      </div>

      {loading && <div className={styles.muted}>Analizando…</div>}

      {report && (
        <>
          <div className={styles.chips}>
            <span className={styles.chipError}>{report.counts.error} errores</span>
            <span className={styles.chipWarn}>{report.counts.warning} advertencias</span>
            <span className={styles.chipInfo}>{report.counts.info} info</span>
          </div>

          {report.fixes_omitted && (
            <div className={styles.muted}>YAML grande: los fixes se omitieron.</div>
          )}

          {ordered.length === 0 && <div className={styles.ok}>Sin observaciones. ✓</div>}

          <ul className={styles.list}>
            {ordered.map((f, i) => (
              <li key={`${f.code}-${i}`} className={styles.item}>
                <button
                  type="button"
                  className={styles.findingBtn}
                  onClick={() => onHighlightLine(f.line ?? undefined)}
                >
                  <span className={sevClass(f.severity)}>[{f.code}]</span> {f.message}
                  {f.line != null && <span className={styles.lineNo}> — línea {f.line}</span>}
                </button>
                {f.fix && (
                  <details className={styles.fixDetails}>
                    <summary className={styles.fixSummary}>Ver fix…</summary>
                    <div className={styles.fixDesc}>{f.fix.description}</div>
                    <pre className={styles.diff}>
                      {buildDiffLines(currentYaml, f.fix.new_yaml).rows.map((r, k) => (
                        <div key={k} className={diffClass(r.kind)}>
                          {diffPrefix(r.kind)}
                          {r.text}
                        </div>
                      ))}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ul>

          <button type="button" className={styles.planBtn} onClick={() => void loadPlan()}>
            Plan de ejecución
          </button>

          {plan && (
            <div className={styles.plan}>
              {!plan.ok && <div className={styles.sevError}>Hay un ciclo: el plan no se puede resolver.</div>}
              {plan.phases.map((phase, pi) => (
                <div key={pi} className={styles.phase}>
                  <span className={styles.phaseLabel}>Fase {pi + 1}:</span>{' '}
                  {phase.map((n) => n.name).join(' ∥ ')}
                  {phase.some((n) => n.warnings.length > 0) && (
                    <span className={styles.muted}> (con condicionales)</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

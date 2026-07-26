import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  COMMIT_BLOCK_COPY,
  MAX_EDIT_LINES,
  canCommit,
  canRenderDiff,
  emptyEditForm,
  formatPreservation,
  isPlanRequestReady,
  prefillOnlyEmpty,
  summarizeHunks,
  type EditFormState,
  type Hunk,
} from '../pipelineEditModel';

const completo = (over: Partial<EditFormState> = {}): EditFormState => ({
  ...emptyEditForm(),
  beforeYaml: 'stages: []\n',
  repoPath: 'pipelines/ci-cd-online.yml',
  verb: 'add_step',
  targetPath: 'stages[0].jobs[0].steps',
  taskRef: 'PublishCodeCoverageResults@2',
  ...over,
});

describe('plan 250 F4 — modelo puro de la edición', () => {
  it('1. isPlanRequestReady exige taskRef para add_step', () => {
    expect(isPlanRequestReady(completo({ taskRef: null }))).toBe(false);
    expect(isPlanRequestReady(completo())).toBe(true);
  });

  it('2. isPlanRequestReady no exige taskRef para remove_step', () => {
    const s = completo({ verb: 'remove_step', taskRef: null, anchorRef: 'VSBuild@1' });
    expect(isPlanRequestReady(s)).toBe(true);
  });

  it('3. prefillOnlyEmpty NO pisa un displayName que ya tiene texto', () => {
    const s = completo({ displayName: 'lo que escribí yo' });
    expect(prefillOnlyEmpty(s, { displayName: 'sugerencia' }).displayName).toBe('lo que escribí yo');
  });

  it('4. prefillOnlyEmpty sí rellena un displayName vacío', () => {
    const s = completo({ displayName: '   ' });
    expect(prefillOnlyEmpty(s, { displayName: 'sugerencia' }).displayName).toBe('sugerencia');
  });

  it('5. summarizeHunks describe inserciones y el caso vacío', () => {
    const h: Hunk[] = [{ start_line: 10, end_line: 9, before: [], after: ['- task: X@1'], reason: 'r' }];
    expect(summarizeHunks(h)).toBe('1 bloque agregado');
    expect(summarizeHunks([])).toBe('sin cambios');
  });

  it('6. canRenderDiff es false por encima de MAX_EDIT_LINES (buildDiffLines no tiene cap propio)', () => {
    const chico = 'a\n'.repeat(10);
    const gigante = 'a\n'.repeat(MAX_EDIT_LINES + 5);
    expect(canRenderDiff(chico, chico)).toBe(true);
    expect(canRenderDiff(chico, gigante)).toBe(false);
    expect(canRenderDiff(gigante, chico)).toBe(false);
  });

  it('7. summarizeHunks es puro: 2 llamadas dan el mismo string', () => {
    const h: Hunk[] = [
      { start_line: 3, end_line: 5, before: ['a'], after: ['b'], reason: 'r' },
      { start_line: 9, end_line: 8, before: [], after: ['c'], reason: 'r' },
    ];
    expect(summarizeHunks(h)).toBe(summarizeHunks(h));
    expect(summarizeHunks(h)).toContain('1 bloque agregado');
  });

  it('8. el estado inicial del formulario no habilita el commit', () => {
    const r = canCommit(emptyEditForm(), { pipeline_nl_edit_commit_enabled: true }, {
      reviewOk: true,
      confirmChecked: true,
      hasHunks: true,
    });
    expect(r.allowed).toBe(false);
    expect(r.reason).toBe('formulario_incompleto');
  });

  it('9. C5 — sin beforeYaml o sin repoPath no hay pedido, aunque el resto esté completo', () => {
    expect(isPlanRequestReady(completo({ beforeYaml: '' }))).toBe(false);
    expect(isPlanRequestReady(completo({ repoPath: '   ' }))).toBe(false);
  });

  it('10. C2 — con la flag de commit apagada NO se puede commitear, y el modelo dice por qué', () => {
    const r = canCommit(completo(), { pipeline_nl_edit_commit_enabled: false }, {
      reviewOk: true,
      confirmChecked: true,
      hasHunks: true,
    });
    expect(r.allowed).toBe(false);
    expect(r.reason).toBe('flag_commit_off');
    expect(COMMIT_BLOCK_COPY.flag_commit_off).toContain('STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED');
    // y con la flag encendida y todo en verde, sí
    const ok = canCommit(completo(), { pipeline_nl_edit_commit_enabled: true }, {
      reviewOk: true,
      confirmChecked: true,
      hasHunks: true,
    });
    expect(ok.allowed).toBe(true);
  });

  it('11. formatPreservation nombra la construcción perdida', () => {
    const sano = formatPreservation({
      ok: true,
      comments_before: 47,
      comments_after: 47,
      unsupported_lost: [],
      lines_untouched: 119,
      lines_total_before: 127,
      detail: '',
    });
    expect(sano).toContain('Se preservan 47/47 comentarios');
    expect(sano).toContain('119 de 127');

    const roto = formatPreservation({
      ok: false,
      comments_before: 47,
      comments_after: 40,
      unsupported_lost: ['matrix'],
      lines_untouched: 100,
      lines_total_before: 127,
      detail: 'se perderian 7 comentario(s)',
    });
    expect(roto).toContain('matrix');
    expect(roto).toContain('se perderian 7');
  });

  it('12. el panel se monta por DEVOPS_SECTIONS y no toca PipelineBuilderSection (C1)', () => {
    const raiz = join(__dirname, '..', '..');
    const page = readFileSync(join(raiz, 'pages', 'DevOpsPage.tsx'), 'utf-8');
    expect(page).toContain("id: 'editar-pipeline'");
    expect(page).toContain("healthKey: 'pipeline_nl_edit_enabled'");
    expect(page).toContain("gateFlagKey: 'STACKY_PIPELINE_NL_EDIT_ENABLED'");

    const panel = readFileSync(
      join(raiz, 'components', 'devops', 'PipelineEditNlPanel.tsx'),
      'utf-8',
    );
    expect(panel).not.toContain('PipelineBuilderSection');
    // gotcha de la casa: en un .tsx NUEVO el uiDebtRatchet tiene alcance 0
    expect(panel).not.toContain('style={{');
  });
});

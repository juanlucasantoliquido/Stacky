/**
 * doctorModel.test.ts — Plan 96 F4. vitest, TS puro.
 */
import { describe, expect, it } from 'vitest';
import { buildAgentPrompt, summaryLine, type DoctorJob } from './doctorModel';

function makeJob(overrides: Partial<DoctorJob> = {}): DoctorJob {
  return {
    job_id: '1',
    name: 'build',
    stage: 'build',
    web_url: null,
    diagnosis: { matches: [], snippet: '' },
    ...overrides,
  };
}

describe('buildAgentPrompt', () => {
  it('prompt_contains_project_titles_and_confirmo', () => {
    const jobs: DoctorJob[] = [
      makeJob({
        name: 'build-step',
        diagnosis: {
          matches: [
            { id: 'cmd_not_found', title: 'Un comando del script no existe en el runner', hint: 'algo', line_no: 3 },
          ],
          snippet: 'robocopy: command not found',
        },
      }),
    ];
    const prompt = buildAgentPrompt('mi-proyecto', jobs);

    expect(prompt).toContain('mi-proyecto');
    expect(prompt).toContain('build-step');
    expect(prompt).toContain('Un comando del script no existe en el runner');
    expect(prompt).toContain('robocopy: command not found');
    expect(prompt).toContain('CONFIRMO');
  });

  it('prompt_fallback_sin_patron', () => {
    const jobs: DoctorJob[] = [
      makeJob({ name: 'mystery-step', diagnosis: { matches: [], snippet: 'algo raro pasó' } }),
    ];
    const prompt = buildAgentPrompt('otro-proyecto', jobs);

    expect(prompt).toContain('mystery-step');
    expect(prompt).toContain('sin patron reconocido');
    expect(prompt).toContain('CONFIRMO');
  });
});

describe('summaryLine', () => {
  it('summary_line_joins_titles', () => {
    const jobs: DoctorJob[] = [
      makeJob({
        name: 'job1',
        diagnosis: {
          matches: [{ id: 'cmd_not_found', title: 'comando inexistente', hint: '', line_no: 1 }],
          snippet: '',
        },
      }),
      makeJob({
        name: 'job2',
        diagnosis: {
          matches: [{ id: 'file_not_found', title: 'archivo no encontrado', hint: '', line_no: 1 }],
          snippet: '',
        },
      }),
    ];
    const summary = summaryLine(jobs);

    expect(summary).toContain('2 jobs fallaron');
    expect(summary).toContain('comando inexistente');
    expect(summary).toContain('archivo no encontrado');
  });
});

/**
 * Tests para PrReviewerSection (Plan 110 F7).
 * NOTA: el entorno no tiene @testing-library/react (gap preexistente, ver Plan 107),
 * así que se verifica el export + los criterios binarios por contenido de fuente,
 * igual que PipelineBuilderSection.test.ts. El gate real es tsc + los tests backend.
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';

const SRC = 'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PrReviewerSection.tsx';
const read = () => fs.readFileSync(SRC, 'utf-8');

describe('PrReviewerSection - F7 export', () => {
  it('componente PrReviewerSection exportado', async () => {
    const { PrReviewerSection } = await import('../PrReviewerSection');
    expect(PrReviewerSection).toBeDefined();
  });

  it('PrReview client expone list/detail/reviewHaiku/reviewLocal/actions/models/execute', async () => {
    const { PrReview } = await import('../../../api/endpoints');
    for (const k of ['list', 'detail', 'reviewHaiku', 'reviewLocal', 'actions', 'models', 'execute']) {
      expect(typeof (PrReview as Record<string, unknown>)[k]).toBe('function');
    }
  });
});

describe('Criterios binarios F7 (verificables por fuente)', () => {
  it('renderiza la lista de PRs desde PrReview.list', () => {
    const c = read();
    expect(c).toContain('PrReview.list');
    expect(c).toContain('merge_requests');
  });

  it('muestra resumen, hallazgos y badge de acción recomendada de la revisión Haiku', () => {
    const c = read();
    expect(c).toContain('haikuReview.summary');
    expect(c).toContain('haikuReview.findings');
    expect(c).toContain('recommended_action.label');
  });

  it('merge exige el checkbox literal antes de habilitar Ejecutar', () => {
    const c = read();
    expect(c).toContain('Confirmo que quiero mergear esta PR');
    expect(c).toContain('disabled={!confirmMerge}');
    expect(c).toContain("confirm_merge: action === 'merge'");
  });

  it('la revisión local envía la pregunta del operador', () => {
    const c = read();
    expect(c).toContain('PrReview.reviewLocal(activeProject, selected.id, question)');
  });

  it('el botón approve solo aparece si actions incluye approve', () => {
    const c = read();
    expect(c).toContain("actions.includes('approve')");
  });

  it('C1 — el botón Haiku queda deshabilitado hasta tildar "confirmo el envío"', () => {
    const c = read();
    expect(c).toContain('Reviso el contenido y confirmo el envío');
    expect(c).toContain('disabled={!confirmExternalSend || haikuBusy}');
    expect(c).toContain('Ver exactamente qué se envía a Copilot/GitHub');
  });

  it('v2.1 — acción separada "solo con modelo local" SIN checkbox de envío externo', () => {
    const c = read();
    expect(c).toContain('Revisar solo con modelo local (nada sale de tu máquina)');
    // el bloque local no depende de confirmExternalSend
    const localIdx = c.indexOf('localBlock');
    const localSlice = c.slice(localIdx);
    expect(localSlice).not.toContain('confirmExternalSend');
  });

  it('aviso de privacidad siempre presente', () => {
    const c = read();
    expect(c).toContain('PRIVACY_NOTICE');
    expect(c).toContain('diff) se envía al modelo');
  });
});

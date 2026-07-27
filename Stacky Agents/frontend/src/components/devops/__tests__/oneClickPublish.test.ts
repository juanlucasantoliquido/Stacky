/**
 * oneClickPublish.test.ts — Plan 102 F2 + F3 + F4.
 *
 * Fija el cableado del modal. La lógica de la cadena vive en
 * `devops/publishChain.ts` y se prueba allá (10 casos deterministas).
 *
 * Gap declarado: `@testing-library/react` y `jsdom` NO están instalados ⇒ el
 * render real no es verificable; la interacción se verifica a mano.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');

const MODAL = read('components/devops/OneClickPublishModal.tsx');
const CHAIN = read('devops/publishChain.ts');
const COMMIT_MODAL = read('components/devops/CommitPipelineModal.tsx');
const PUBLICATIONS = read('components/devops/PublicationsSection.tsx');
const ENVIRONMENTS = read('components/devops/EnvironmentsSection.tsx');

describe('Plan 102 F2 — modal', () => {
  it('1. el modal usa runPublishChain (no reimplementa la cadena)', () => {
    expect(MODAL).toContain('runPublishChain');
    expect(MODAL).toContain("from '../../devops/publishChain'");
  });

  it('2. exige un confirm explícito antes de tocar nada (HITL)', () => {
    expect(MODAL).toContain('if (!confirmado || !spec || corriendo) return;');
    expect(MODAL).toContain('disabled={!confirmado || !spec || corriendo}');
  });

  it('3. CONTROL DE C1 — no bloquea ADO ni menciona la limitación del 501', () => {
    // El v1 definía `adoCommitBlocked` y bloqueaba todo preset con target='ado'
    // creyéndole a un copy stale. El commit ADO es real desde el Plan 95 F1.a.
    expect(MODAL).not.toContain('adoCommitBlocked');
    expect(MODAL).not.toContain('501');
    expect(MODAL.toLowerCase()).not.toContain('render-only');
    // Y la cadena tampoco puede discriminar: ni siquiera recibe el target.
    expect(CHAIN).not.toContain('adoCommitBlocked');
  });

  it('4. CONTROL DE C3 — deuda UI cero en el archivo nuevo', () => {
    expect(MODAL).not.toMatch(/style=\{\{/);
    expect(MODAL).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    // Primitivas de la casa, nunca <input> crudo.
    expect(MODAL).toContain("from '../ui'");
    expect(MODAL).toContain('<Checkbox');
    expect(MODAL).toContain('<Input');
    expect(MODAL).not.toMatch(/<input\s/);
  });

  it('5. monta el preflightSlot ENTRE el resumen y el confirm', () => {
    expect(MODAL).toContain('preflightSlot');
    const iSlot = MODAL.indexOf('{preflightSlot}');
    expect(iSlot).toBeGreaterThan(MODAL.indexOf('Branch destino'));
    expect(iSlot).toBeLessThan(MODAL.indexOf('<Checkbox'));
  });

  it('6. CERO rollback: no existe ninguna dependencia que deshaga', () => {
    const codigo = CHAIN
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .filter((l) => !l.trim().startsWith('//'))
      .join('\n');
    expect(codigo).not.toMatch(/\brollback\b|\bundo\b|\brevert\b/i);
  });

  it('6.bis. el preflight NO está cableado como veto (C5, HITL del plan 93)', () => {
    // `beforeCommit` se declara como `never` a propósito: el PreflightPanel es
    // informativo y NUNCA bloquea. Cablear un veto violaría el HITL de ese plan.
    expect(CHAIN).toContain('beforeCommit?: never');
  });
});

describe('Plan 102 F3 — montaje gateado', () => {
  it('7. las 2 secciones gatean el botón por las 3 flags', () => {
    for (const [nombre, src] of [
      ['PublicationsSection', PUBLICATIONS],
      ['EnvironmentsSection', ENVIRONMENTS],
    ] as const) {
      expect(src, `${nombre} sin gate de la flag propia`).toContain(
        'ctx.health.one_click_publish_enabled === true',
      );
      expect(src, `${nombre} sin gate del generador`).toContain(
        'ctx.health.generator_enabled === true',
      );
      expect(src, `${nombre} sin gate del disparo`).toContain(
        'ctx.health.trigger_enabled === true',
      );
      expect(src).toContain('OneClickPublishModal');
    }
  });

  it('8. los caminos viejos siguen intactos (backward-compatible duro)', () => {
    for (const src of [PUBLICATIONS, ENVIRONMENTS]) {
      expect(src).toContain('CommitPipelineModal');
      expect(src).toContain('TriggerPipelineSection');
    }
  });
});

describe('Plan 102 F4 — centinela del copy stale', () => {
  it('9. CommitPipelineModal ya no afirma la limitación del 501', () => {
    // Esa mentira en la UI se propagó a un plan y casi se convierte en regresión.
    expect(COMMIT_MODAL).not.toContain('commit devuelve 501');
    expect(COMMIT_MODAL).not.toContain('Render-only v1');
  });
});

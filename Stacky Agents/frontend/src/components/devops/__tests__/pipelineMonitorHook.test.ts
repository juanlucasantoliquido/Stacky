/**
 * pipelineMonitorHook.test.ts — Plan 103 F2 + F3.
 *
 * Fija el CABLEADO del monitor. La lógica vive en `devops/pipelineMonitor.ts` y se
 * prueba allá (11 casos deterministas).
 *
 * Gap declarado: `@testing-library/react` y `jsdom` NO están instalados, así que
 * no se puede montar el hook ni el badge. Estos greps fijan las invariantes que
 * el plan considera críticas; la interacción la cubre la verificación manual §F4.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');

const HOOK = read('components/devops/useDevopsPipelineMonitor.ts');
const HEADER = read('pages/DevOpsHeaderV2.tsx');
const SHELL = read('pages/DevOpsPage.tsx');
const TRIGGER = read('components/devops/TriggerPipelineSection.tsx');

describe('Plan 103 F2 — hook con guard de visibilidad', () => {
  it('1. el hook existe y es una función', async () => {
    const mod = await import('../useDevopsPipelineMonitor');
    expect(typeof mod.useDevopsPipelineMonitor).toBe('function');
  });

  it('2. CONTROL DE C1 — el hook gatea por visibilidad del documento y REANUDA', () => {
    // Vive en el shell (no puede usar ctx.visible), así que su guard es la pestaña.
    expect(HOOK).toContain('visibilityState');
    // Sin el listener, el sondeo se pausaría y no volvería nunca: peor que sondear
    // de más, porque el badge quedaría congelado mintiendo.
    expect(HOOK).toContain('visibilitychange');
    // Y `visible` tiene que estar EN LAS DEPS del efecto o no se re-evalúa.
    expect(HOOK).toMatch(/\[[^\]]*\bvisible\b[^\]]*\]/);
  });

  it('3. CONTROL DE C5 — el 429 del cap de polls no se trata como fallo', () => {
    expect(HOOK).toContain('isPollCapError');
    expect(HOOK).toContain('bumpAttempt');
  });

  it('4. se detiene en estado terminal y no re-arranca solo', () => {
    expect(HOOK).toContain('isTerminalStatus');
    expect(HOOK).toContain('if (isTerminalStatus(status)) return;');
  });

  it('5. usa backoff re-armado, NO un intervalo fijo', () => {
    expect(HOOK).toContain('computeBackoffMs');
    expect(HOOK).not.toContain('setInterval(');
    expect(HOOK).toContain('setTimeout(');
  });
});

describe('Plan 103 F3 — badge en el header y delegación', () => {
  it('6. el badge vive en el header (funciona con cockpit ON y OFF)', () => {
    expect(HEADER).toContain('useDevopsMonitorStore');
    expect(HEADER).toContain('formatMonitorStatus');
    // Solo-lectura + descarte HITL.
    expect(HEADER).toContain('clear');
    // No muestra el pipeline de OTRO proyecto.
    expect(HEADER).toContain('appliesToProject');
  });

  it('7. el shell invoca el hook gateado por la flag', () => {
    expect(SHELL).toContain('useDevopsPipelineMonitor(monitorOn)');
    expect(SHELL).toContain("ctx.health.pipeline_monitor_enabled === true");
  });

  it('8. CONTROL DE C7 — sin doble polling: con la flag ON el poller local no corre', () => {
    expect(TRIGGER).toContain('if (monitorOn) return;');
    // El registro en el store existe (si no, el badge nunca aparecería).
    expect(TRIGGER).toContain('setLastPipeline({');
  });

  it('9. CONTROL DEL 239 F6 — `ctx.visible !== false` sigue presente DOS veces', () => {
    // Los dos pollers de la sección (bitácora y recién-disparado). Si este número
    // baja, alguien rompió la doctrina de sondeo del plan 239.
    const n = (TRIGGER.match(/ctx\.visible !== false/g) ?? []).length;
    expect(n).toBe(2);
    // Y el poller de la BITÁCORA quedó intacto (fuera de scope del 103).
    expect(TRIGGER).toContain('if (ctx.visible === false) return;');
  });

  it('10. el JSON crudo dejó de ser la única forma de leer el estado', () => {
    expect(TRIGGER).toContain('formatMonitorStatus');
    // Con la flag OFF el JSON sigue ahí: la degradación es real, no un borrado.
    expect(TRIGGER).toContain('JSON.stringify(monitorStatus, null, 2)');
  });

  it('11. deuda UI cero en el badge (ni inline styles ni hex)', () => {
    expect(HEADER).not.toMatch(/style=\{\{/);
    expect(HEADER).not.toMatch(/#[0-9a-fA-F]{3,6}/);
    const css = read('pages/DevOpsPage.module.css');
    for (const cls of ['.pipeBadge', '.pipeBadgeSuccess', '.pipeBadgeError', '.pipeBadgeClose']) {
      expect(css, `falta ${cls}`).toContain(cls);
    }
  });
});

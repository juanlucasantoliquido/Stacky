// Plan 198 F2 — tests puros (vitest, sin @testing-library — gap conocido).
import { describe, it, expect } from 'vitest';
import { applyRow, driftBadge, type EnvApply } from './envApplyLedger';

function mkApply(over: Partial<EnvApply> = {}): EnvApply {
  return {
    root: 'C:/amb',
    server_alias: null,
    paths: ['a/b'],
    fingerprint: 'FP',
    sandbox_active: false,
    result_ok: true,
    created_count: 3,
    applied_at: '2026-07-18T10:00:00+00:00',
    source: 'stacky',
    ...over,
  };
}

describe('applyRow', () => {
  it('formatea apply LOCAL exitoso', () => {
    expect(applyRow(mkApply())).toBe('2026-07-18T10:00:00+00:00 · Local · 3 creadas · OK');
  });

  it('usa el alias del servidor cuando es remoto', () => {
    expect(applyRow(mkApply({ server_alias: 'srv1', created_count: 5 }))).toBe(
      '2026-07-18T10:00:00+00:00 · srv1 · 5 creadas · OK',
    );
  });

  it('marca FALLÓ cuando result_ok es false', () => {
    expect(applyRow(mkApply({ result_ok: false, created_count: 0 }))).toBe(
      '2026-07-18T10:00:00+00:00 · Local · 0 creadas · FALLÓ',
    );
  });
});

describe('driftBadge', () => {
  it('null → none (sin texto)', () => {
    expect(driftBadge(null)).toEqual({ tone: 'none', text: '' });
  });

  it('true → warn con el texto exacto', () => {
    expect(driftBadge(true)).toEqual({
      tone: 'warn',
      text: 'La definición del layout cambió desde el último apply — replanificá',
    });
  });

  it('false → ok', () => {
    expect(driftBadge(false)).toEqual({
      tone: 'ok',
      text: 'Definición del layout igual al último apply',
    });
  });
});

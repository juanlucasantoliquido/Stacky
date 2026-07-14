import { describe, it, expect } from 'vitest';
import { mapTestResultToState } from './serversTable';

describe('mapTestResultToState', () => {
  it('undefined ⇒ sin probar (none)', () => {
    expect(mapTestResultToState(undefined)).toEqual({ tone: 'none', label: 'sin probar' });
  });
  it('ok ⇒ Alcanzable', () => {
    expect(mapTestResultToState({ ok: true, detail: 'WinRM 5985 abierto' })).toEqual({ tone: 'ok', label: 'Alcanzable' });
  });
  it('falla ⇒ warn con el detail', () => {
    expect(mapTestResultToState({ ok: false, detail: 'WinRM 5985 cerrado' })).toEqual({ tone: 'warn', label: 'WinRM 5985 cerrado' });
  });
  it('falla sin detail ⇒ warn con fallback "No alcanzable"', () => {
    expect(mapTestResultToState({ ok: false })).toEqual({ tone: 'warn', label: 'No alcanzable' });
  });
});

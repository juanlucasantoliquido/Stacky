/**
 * ConnectionHealthStrip.test.tsx — Plan 116 F3.
 *
 * NOTA DE ENTORNO (bloqueo preexistente): sin `@testing-library/react`/jsdom
 * (mismo gap que RemoteConsoleSection.test.tsx). Test-first, listo para correr.
 * La lógica pura (peor estado por grupo / accionables) está cubierta por
 * connectionHealth.test.ts que SÍ corre en vitest.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { ConnectionHealthStrip } from './ConnectionHealthStrip';
import { DevOps } from '../../api/endpoints';

vi.mock('../../api/endpoints', () => ({
  DevOps: { connectionsHealth: vi.fn(), connectionsCheck: vi.fn() },
}));

function wrap(node: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe('ConnectionHealthStrip', () => {
  it('never_run shows CTA', async () => {
    (DevOps.connectionsHealth as any).mockResolvedValue({ status: 'never_run', stale: false, snapshot: null });
    wrap(<ConnectionHealthStrip onGotoSection={() => {}} />);
    expect(await screen.findByText(/Nunca corrido/)).toBeTruthy();
  });

  it('check button triggers POST once', async () => {
    (DevOps.connectionsHealth as any).mockResolvedValue({ status: 'never_run', stale: false, snapshot: null });
    (DevOps.connectionsCheck as any).mockResolvedValue({ status: 'ready', stale: false,
      snapshot: { generated_at: '', duration_ms: 1, results: [], summary: { ok: 0, warn: 0, fail: 0, skip: 0 } } });
    wrap(<ConnectionHealthStrip onGotoSection={() => {}} />);
    fireEvent.click(await screen.findByText('Diagnosticar'));
    expect(DevOps.connectionsCheck).toHaveBeenCalledTimes(1);
  });
});

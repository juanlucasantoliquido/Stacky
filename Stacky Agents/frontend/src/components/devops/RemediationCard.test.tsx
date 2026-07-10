/**
 * RemediationCard.test.tsx — Plan 116 F3.
 *
 * NOTA DE ENTORNO (bloqueo preexistente, NO introducido por este plan): este
 * checkout no tiene `@testing-library/react` ni jsdom (mismo gap que bloquea a
 * RemoteConsoleSection.test.tsx / DirTreePreview.test.tsx del plan 107). El test
 * queda escrito test-first, listo para correr apenas se resuelva el gap. La
 * verificación de tipos (tsc --noEmit) sí corre y cubre el componente; la lógica
 * pura del strip está cubierta por connectionHealth.test.ts (SÍ corre en vitest).
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { RemediationCard } from './RemediationCard';
import type { ConnectionDiagResult } from '../../api/endpoints';

function auth401(): ConnectionDiagResult {
  return {
    target: 'tracker', target_label: 'GitLab', group: 'tracker', status: 'fail',
    code: 'AUTH_401', detail: 'token rechazado', latency_ms: 10,
    remediation: {
      title: 'Credenciales inválidas o vencidas',
      cause: 'GitLab rechazó la autenticación (401).',
      steps: ['Regenerá el token', 'Pegalo y guardá'],
      action: { kind: 'open_url', url: 'https://x/-/user_settings/personal_access_tokens' },
    },
  };
}

describe('RemediationCard', () => {
  it('renders title cause and steps', () => {
    render(<RemediationCard result={auth401()} />);
    expect(screen.getByText(/Credenciales inválidas/)).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('copy_command writes clipboard', () => {
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    const r = { ...auth401(), code: 'DNS_FAIL',
      remediation: { title: 'x', cause: 'y', steps: ['a', 'b'],
        action: { kind: 'copy_command' as const, command: 'ping srv01' } } };
    render(<RemediationCard result={r} />);
    fireEvent.click(screen.getByText('Copiar comando'));
    expect(writeText).toHaveBeenCalledWith('ping srv01');
  });

  it('retry calls onRetry', () => {
    const onRetry = vi.fn();
    const r = { ...auth401(),
      remediation: { title: 'x', cause: 'y', steps: ['a', 'b'], action: { kind: 'retry' as const } } };
    render(<RemediationCard result={r} onRetry={onRetry} />);
    fireEvent.click(screen.getByText('Reintentar'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('null remediation renders nothing', () => {
    const { container } = render(
      <RemediationCard result={{ ...auth401(), status: 'ok', remediation: null }} />);
    expect(container.firstChild).toBeNull();
  });
});

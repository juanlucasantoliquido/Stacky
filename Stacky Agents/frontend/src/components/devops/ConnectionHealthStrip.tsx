/**
 * ConnectionHealthStrip.tsx — Plan 116 F3.
 *
 * Tira de salud de conexiones (shell del panel DevOps): 4 chips por grupo con el
 * peor estado, botón "Diagnosticar" (HITL, sin polling) y panel expandible de
 * tarjetas de remediación. Gateada en DevOpsPage por health.connection_doctor_enabled.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DevOps } from '../../api/endpoints';
import type { ConnectionsHealthResponse } from '../../api/endpoints';
import { worstStatus, actionableResults, type GroupId, type ChipStatus } from './connectionHealth';
import { RemediationCard } from './RemediationCard';
import styles from './devops.module.css';

interface Props {
  onGotoSection: (sectionId: string) => void;
}

const GROUPS: { id: GroupId; label: string }[] = [
  { id: 'tracker', label: 'Tracker' },
  { id: 'servers', label: 'Servidores' },
  { id: 'clis', label: 'CLIs' },
  { id: 'credentials', label: 'Credenciales' },
];

const CHIP_CLASS: Record<ChipStatus, string> = {
  fail: styles.healthChipFail,
  warn: styles.healthChipWarn,
  ok: styles.healthChipOk,
  skip: styles.healthChipSkip,
};

export function ConnectionHealthStrip({ onGotoSection }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const healthQuery = useQuery({
    queryKey: ['devops-connections-health'],
    queryFn: DevOps.connectionsHealth,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: DevOps.connectionsCheck,
    onSuccess: (d: ConnectionsHealthResponse) =>
      queryClient.setQueryData(['devops-connections-health'], d),
  });

  const snapshot = healthQuery.data?.snapshot ?? null;
  const neverRun = healthQuery.data?.status === 'never_run' || !snapshot;
  const stale = healthQuery.data?.stale === true;
  const pending = mutation.isPending;
  const actionable = actionableResults(snapshot);

  return (
    <div className={styles.healthStrip}>
      {GROUPS.map((g) => {
        const st = worstStatus(snapshot, g.id);
        return (
          <span key={g.id} className={`${styles.healthChip} ${CHIP_CLASS[st]}`}>
            {pending ? <span className={styles.skeletonBar} /> : `${g.label}: ${st === 'skip' ? '—' : st}`}
          </span>
        );
      })}
      <button type="button" disabled={pending} onClick={() => mutation.mutate()}>
        {pending ? 'Diagnosticando…' : 'Diagnosticar'}
      </button>
      <span>
        {neverRun
          ? 'Nunca corrido — click en Diagnosticar'
          : `Último chequeo: ${new Date(snapshot!.generated_at).toLocaleString()} (${snapshot!.duration_ms} ms)`}
        {stale && <span className={styles.healthChipWarn}> desactualizado</span>}
      </span>
      {actionable.length > 0 && (
        <button type="button" onClick={() => setOpen((v) => !v)}>
          {open ? 'Ocultar detalle' : `Ver detalle (${actionable.length})`}
        </button>
      )}
      {open && (
        <div>
          {actionable.map((r) => (
            <RemediationCard
              key={r.target + r.code}
              result={r}
              onRetry={() => mutation.mutate()}
              onGotoSection={onGotoSection}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default ConnectionHealthStrip;

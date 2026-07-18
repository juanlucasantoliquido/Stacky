/**
 * VariablesSection (Plan 94 F4)
 *
 * Sección "Variables" del panel DevOps: caja fuerte de variables del pipeline.
 * Las secretas se crean EN EL TRACKER (GitLab masked / ADO isSecret) — JAMÁS
 * tocan el YAML, el repo, el client_profile ni los logs (riel §3.1 del 91).
 *
 * Contrato §3.7/§3.12 del 87 v3: el gate de flag-off lo hace el SHELL
 * (DevOpsPage) según healthKey/gateFlagKey/gateMessage. Esta sección NO
 * hand-rollea el gate ni menciona su propia flag.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWorkbench } from '../../store/workbench';
import { DevOpsVariables, type CIVariableSummary } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { looksSecret, validateVariableKey, canBeMasked } from '../../devops/variablesModel';
import { useConfirm } from '../ui';
import styles from './devops.module.css';

export interface VariablesSectionProps {
  ctx: DevOpsSectionContext;
}

/**
 * El cliente HTTP (api/client.ts) lanza un Error PLANO
 * (`${status} ${statusText}: ${rawBody}`), sin adjuntar el JSON parseado como
 * propiedad del error (NO existe `error.kind` — sería código muerto). Para
 * distinguir 409 variables_unavailable del resto, hay que parsear el body
 * crudo desde el mensaje.
 */
function parseVariablesError(e: unknown): { unavailable: boolean; message: string | null } {
  if (!(e instanceof Error)) return { unavailable: false, message: null };
  const idx = e.message.indexOf(': ');
  const rawBody = idx >= 0 ? e.message.slice(idx + 2) : '';
  try {
    const parsed = JSON.parse(rawBody);
    return {
      unavailable: parsed?.kind === 'variables_unavailable',
      message: typeof parsed?.error === 'string' ? parsed.error : null,
    };
  } catch {
    return { unavailable: e.message.includes('variables_unavailable'), message: null };
  }
}

export const VariablesSection: React.FC<VariablesSectionProps> = ({ ctx }) => {
  void ctx;
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  const listQuery = useQuery({
    queryKey: ['devops-variables', activeProject],
    queryFn: () => DevOpsVariables.list(activeProject),
    enabled: !!activeProject,
    retry: false,
  });

  const askConfirm = useConfirm();
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const [secret, setSecret] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<CIVariableSummary | null>(null);

  const variables = listQuery.data?.variables ?? [];
  const provider = listQuery.data?.provider;
  const { unavailable, message: unavailableMessage } = parseVariablesError(listQuery.error);

  const keyError = key ? validateVariableKey(key) : null;
  const canSubmit = !!key.trim() && !keyError && !!value;
  const maskingWarning = provider === 'gitlab' && secret && value && !canBeMasked(value);

  const handleKeyChange = (v: string) => {
    setKey(v);
    setSecret(looksSecret(v) || secret);
  };

  const handleCreate = async () => {
    if (!canSubmit) return;
    if (!(await askConfirm({ title: 'Guardar variable', message: `¿Guardar la variable '${key}' en el tracker?`, confirmLabel: 'Guardar' }))) return;
    try {
      setActionError(null);
      const result = await DevOpsVariables.create({ project: activeProject, key, value, secret, confirm: true });
      setLastResult(result);
      setKey('');
      setValue(''); // value NUNCA se guarda en estado tras el submit
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo guardar la variable: ${msg}`);
    }
  };

  const handleDelete = async (k: string) => {
    if (!(await askConfirm({ title: 'Borrar variable', message: `¿Borrar la variable '${k}' del tracker?`, tone: 'danger', confirmLabel: 'Borrar' }))) return;
    try {
      setActionError(null);
      await DevOpsVariables.remove(activeProject, k);
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo borrar la variable: ${msg}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {actionError && <div className={styles.alertError}>{actionError}</div>}

      {unavailable && (
        <div className={styles.alertWarning}>
          {unavailableMessage ?? 'El tracker todavía no puede alojar variables.'}
          {' '}Llevá el pipeline a producción (plan 95) para crear la definition de ADO, o usá GitLab.
        </div>
      )}

      {!unavailable && (
        <div className={styles.panel}>
          <h4 style={{ marginTop: 0 }}>Nueva variable{provider ? ` (${provider})` : ''}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '8px', alignItems: 'center' }}>
            <input
              type="text"
              value={key}
              onChange={(e) => handleKeyChange(e.target.value)}
              placeholder="KEY (ej: DB_PASSWORD)"
              style={{ padding: '8px' }}
            />
            <input
              type={secret ? 'password' : 'text'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="valor"
              style={{ padding: '8px' }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
              <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
              Es secreta 🔒
            </label>
          </div>
          {keyError && <p className={styles.textDanger} style={{ fontSize: '0.85em' }}>{keyError}</p>}
          {maskingWarning && (
            <p className={styles.textWarn} style={{ fontSize: '0.85em' }}>
              Este valor no va a poder enmascararse en los logs de GitLab (reglas de masking).
            </p>
          )}
          <div style={{ marginTop: '8px' }}>
            <button onClick={() => void handleCreate()} disabled={!canSubmit} className={styles.btnSuccess}>
              Guardar
            </button>
          </div>
          {lastResult && lastResult.masked === false && lastResult.is_secret && (
            <p className={styles.textWarn} style={{ fontSize: '0.85em' }}>
              Guardada como secreta pero NO enmascarable en logs de GitLab (el valor no cumple las reglas de
              masking). Ojo: al refrescar esta variable se lista sin candado — limitación del tracker.
            </p>
          )}
        </div>
      )}

      {!unavailable && (
        <div className={styles.panel}>
          <h4 style={{ marginTop: 0 }}>Variables</h4>
          {variables.length === 0 ? (
            <p style={{ opacity: 0.7 }}>Todavía no hay variables cargadas.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {variables.map((v) => (
                <li key={v.key} style={{ borderBottom: '1px solid var(--border-muted)', padding: '8px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                    <span>
                      {v.is_secret && <span title="secreta">🔒 </span>}
                      <strong>{v.key}</strong>
                      {v.is_secret && v.masked === false && (
                        <span className={styles.textWarn} style={{ marginLeft: '6px' }}>
                          no enmascarable
                        </span>
                      )}
                    </span>
                    <button onClick={() => void handleDelete(v.key)} style={{ padding: '4px 10px' }}>
                      Borrar
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * ServersSection (Plan 91 F5)
 *
 * Sección "Servidores" del panel DevOps (plan 87 v3): CRUD de servidores con alias,
 * test de conectividad y conexión RDP 1-click. El password se guarda en Windows
 * Credential Manager (nunca en disco): la UI es write-only.
 *
 * Contrato §3.7/§3.12 del 87 v3: el gate de flag-off lo hace el SHELL (DevOpsPage)
 * según healthKey/gateFlagKey/gateMessage. Esta sección NO hand-rollea el gate ni
 * menciona su propia flag: el shell es la única fuente del aviso de flag-off.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DevOpsServers, type ServerSummary } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';

export interface ServersSectionProps {
  ctx: DevOpsSectionContext;
}

interface FormState {
  alias: string;
  host: string;
  domain: string;
  username: string;
  notes: string;
  password: string;
}

const EMPTY_FORM: FormState = { alias: '', host: '', domain: '', username: '', notes: '', password: '' };

export const ServersSection: React.FC<ServersSectionProps> = ({ ctx }) => {
  const listQuery = useQuery({
    queryKey: ['devops-servers'],
    queryFn: () => DevOpsServers.list(),
    retry: false,
  });

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingAlias, setEditingAlias] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; detail: string }>>({});

  const rdpAvailable = ctx.health.rdp_available === true;
  const keyringAvailable = listQuery.data?.keyring_available ?? true;
  const servers = listQuery.data?.servers ?? [];
  const isEditing = editingAlias !== null;
  const editingServer = servers.find((s) => s.alias === editingAlias) ?? null;

  const canSubmit = !!form.alias.trim() && !!form.host.trim() && !!form.username.trim();

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingAlias(null);
  };

  const handleEdit = (server: ServerSummary) => {
    setEditingAlias(server.alias);
    setForm({
      alias: server.alias,
      host: server.host,
      domain: server.domain,
      username: server.username,
      notes: server.notes,
      password: '', // write-only: vacío = conservar
    });
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    try {
      setActionError(null);
      if (isEditing) {
        const body: { host: string; domain?: string; username: string; notes?: string; password?: string } = {
          host: form.host.trim(),
          domain: form.domain,
          username: form.username.trim(),
          notes: form.notes,
        };
        if (form.password) body.password = form.password; // vacío = conservar (F3)
        await DevOpsServers.update(editingAlias!, body);
      } else {
        await DevOpsServers.create({
          alias: form.alias.trim(),
          host: form.host.trim(),
          domain: form.domain,
          username: form.username.trim(),
          notes: form.notes,
          ...(form.password ? { password: form.password } : {}),
        });
      }
      resetForm();
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo guardar el servidor: ${msg}`);
    }
  };

  const handleRemovePassword = async (server: ServerSummary) => {
    if (!window.confirm(`¿Quitar la contraseña guardada de '${server.alias}'?`)) return;
    try {
      setActionError(null);
      await DevOpsServers.update(server.alias, {
        host: server.host,
        domain: server.domain,
        username: server.username,
        notes: server.notes,
        password: null, // borra la credencial del Credential Manager (C6)
      });
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo quitar la contraseña: ${msg}`);
    }
  };

  const handleDelete = async (alias: string) => {
    if (!window.confirm(`¿Eliminar el servidor '${alias}' y su credencial guardada?`)) return;
    try {
      setActionError(null);
      await DevOpsServers.remove(alias);
      if (editingAlias === alias) resetForm();
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo eliminar el servidor: ${msg}`);
    }
  };

  const handleTest = async (alias: string) => {
    try {
      setActionError(null);
      const res = await DevOpsServers.testConnection(alias);
      setTestResults((prev) => ({ ...prev, [alias]: res }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo probar la conexión: ${msg}`);
    }
  };

  const handleRdp = async (alias: string) => {
    try {
      setActionError(null);
      await DevOpsServers.connectRdp(alias);
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo conectar por RDP: ${msg}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {actionError && (
        <div className="devops-error" style={{ padding: '12px', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '4px', color: '#721c24' }}>
          {actionError}
        </div>
      )}

      {!keyringAvailable && (
        <div style={{ padding: '8px 12px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', color: '#856404' }}>
          keyring no disponible en el backend: los passwords no se pueden guardar (nunca se guardan en texto plano). Instalá keyring==25.6.0.
        </div>
      )}

      {/* Formulario crear/editar */}
      <div style={{ border: '1px solid #dee2e6', borderRadius: '4px', padding: '12px' }}>
        <h4 style={{ marginTop: 0 }}>{isEditing ? `Editar servidor "${editingAlias}"` : 'Nuevo servidor'}</h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <input
            type="text"
            value={form.alias}
            onChange={(e) => setForm({ ...form, alias: e.target.value })}
            placeholder="alias (ej: prod-web1)"
            disabled={isEditing}
            style={{ padding: '8px' }}
          />
          <input
            type="text"
            value={form.host}
            onChange={(e) => setForm({ ...form, host: e.target.value })}
            placeholder="host (ej: srv01.dominio.local)"
            style={{ padding: '8px' }}
          />
          <input
            type="text"
            value={form.domain}
            onChange={(e) => setForm({ ...form, domain: e.target.value })}
            placeholder="dominio (opcional)"
            style={{ padding: '8px' }}
          />
          <input
            type="text"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            placeholder="usuario"
            style={{ padding: '8px' }}
          />
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            placeholder={isEditing ? (editingServer?.has_password ? '•••• (guardada)' : 'sin password') : 'contraseña'}
            style={{ padding: '8px' }}
          />
          <input
            type="text"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="notas (opcional)"
            style={{ padding: '8px' }}
          />
        </div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '8px', alignItems: 'center' }}>
          <button
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            style={{
              padding: '8px 16px',
              backgroundColor: canSubmit ? '#28a745' : '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: canSubmit ? 'pointer' : 'not-allowed',
            }}
          >
            {isEditing ? 'Guardar cambios' : 'Agregar servidor'}
          </button>
          {isEditing && (
            <>
              <button onClick={resetForm} style={{ padding: '8px 16px' }}>Cancelar</button>
              {editingServer?.has_password && (
                <button onClick={() => void handleRemovePassword(editingServer)} style={{ padding: '8px 16px' }}>
                  Quitar password
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Lista de servidores */}
      <div style={{ border: '1px solid #dee2e6', borderRadius: '4px', padding: '12px' }}>
        <h4 style={{ marginTop: 0 }}>Servidores</h4>
        {servers.length === 0 ? (
          <p style={{ opacity: 0.7 }}>Todavía no cargaste ningún servidor.</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {servers.map((s) => {
              const test = testResults[s.alias];
              return (
                <li key={s.alias} style={{ borderBottom: '1px solid #eee', padding: '8px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                    <span>
                      <strong>{s.alias}</strong>{' '}
                      <span style={{ opacity: 0.8 }}>
                        {s.domain ? `${s.domain}\\${s.username}` : s.username} @ {s.host}
                      </span>{' '}
                      {s.has_password ? (
                        <span style={{ color: '#155724' }}>• credencial guardada</span>
                      ) : (
                        <span style={{ color: '#6c757d' }}>• sin password</span>
                      )}
                      {s.notes && <span style={{ opacity: 0.6 }}> — {s.notes}</span>}
                    </span>
                    <span style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      <button onClick={() => handleEdit(s)} style={{ padding: '4px 10px' }}>Editar</button>
                      <button onClick={() => void handleDelete(s.alias)} style={{ padding: '4px 10px' }}>Eliminar</button>
                      <button onClick={() => void handleTest(s.alias)} style={{ padding: '4px 10px' }}>Probar conexión</button>
                      {rdpAvailable && (
                        <button
                          onClick={() => void handleRdp(s.alias)}
                          style={{ padding: '4px 10px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '3px' }}
                        >
                          Conectar por RDP
                        </button>
                      )}
                    </span>
                  </div>
                  {s.last_connected_at && (
                    <div
                      style={{ fontSize: '0.8em', opacity: 0.7 }}
                      title="fecha del último lanzamiento de mstsc, no del login"
                    >
                      Última conexión: {new Date(s.last_connected_at).toLocaleString()}
                    </div>
                  )}
                  {test && (
                    <div style={{ fontSize: '0.85em', color: test.ok ? '#155724' : '#721c24' }}>
                      {test.detail}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};

/**
 * DevOpsAgentSection (Plan 90 F3)
 *
 * Sección "Agente DevOps" del panel DevOps (plan 87 v3). Abre conversaciones
 * multi-turno con el agente DevOps y reusa el CodexConsoleDock EXISTENTE como
 * chat (cero UI de chat nueva).
 *
 * Contrato de extensión 87 F4/§3.12 (C6 v3): el gate de flag-off lo hace el SHELL
 * (DevOpsPage) vía FlagGateBanner según healthKey/gateFlagKey/gateMessage. Esta
 * sección se monta SOLO con la flag ON, por lo que NO contiene ningún aviso
 * hand-rolled de flag-off. El único aviso propio es OPERACIONAL (resume de sesión),
 * no un gate de flag.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWorkbench } from '../../store/workbench';
import { Projects } from '../../api/endpoints';
import { DevOpsAgentApi } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';

export interface DevOpsAgentSectionProps {
  ctx: DevOpsSectionContext;
}

type CliRuntime = 'claude_code_cli' | 'codex_cli';

export const DevOpsAgentSection: React.FC<DevOpsAgentSectionProps> = ({ ctx }) => {
  // Defensa trivial (C6 v3): early-return silencioso si por algún motivo se montó
  // con la flag OFF. SIN mensaje: el shell es la única fuente del texto de flag-off.
  if (ctx.health.agent_enabled !== true) return null;

  return <DevOpsAgentSectionBody ctx={ctx} />;
};

const DevOpsAgentSectionBody: React.FC<DevOpsAgentSectionProps> = ({ ctx }) => {
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);

  const projectsQuery = useQuery({
    queryKey: ['projects-list-devops-agent'],
    queryFn: () => Projects.list(),
    retry: false,
  });

  const [project, setProject] = useState<string>(activeProjectObj?.name ?? '');
  const [runtime, setRuntime] = useState<CliRuntime>('claude_code_cli');
  const [message, setMessage] = useState<string>('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [continueDraft, setContinueDraft] = useState<Record<number, string>>({});

  const listQuery = useQuery({
    queryKey: ['devops-agent-conversations', project || null],
    queryFn: () => DevOpsAgentApi.list(project || undefined),
    retry: false,
  });

  const projectOptions = projectsQuery.data?.projects ?? [];
  const canStart = !!project && !!message.trim();

  const handleStart = async () => {
    if (!canStart) return;
    try {
      setActionError(null);
      const res = await DevOpsAgentApi.start({ project, message: message.trim(), runtime });
      setCodexConsoleExecution(res.execution_id);
      setMessage('');
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo iniciar la conversación: ${msg}`);
    }
  };

  const handleOpenConsole = (executionId: number | null) => {
    if (executionId == null) return;
    setCodexConsoleExecution(executionId);
  };

  const handleContinue = async (conversationId: number) => {
    const text = (continueDraft[conversationId] ?? '').trim();
    if (!text) return;
    try {
      setActionError(null);
      const res = await DevOpsAgentApi.message(conversationId, text);
      setCodexConsoleExecution(res.execution_id);
      setContinueDraft((prev) => ({ ...prev, [conversationId]: '' }));
      void listQuery.refetch();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo continuar la conversación: ${msg}`);
    }
  };

  const resumeEnabled = listQuery.data?.resume_enabled ?? false;
  const conversations = listQuery.data?.conversations ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {actionError && (
        <div style={{ padding: '12px', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '4px', color: '#721c24' }}>
          No se pudo completar la acción: {actionError}
        </div>
      )}

      {/* Nueva conversación */}
      <div style={{ border: '1px solid #dee2e6', borderRadius: '4px', padding: '12px' }}>
        <h4 style={{ marginTop: 0 }}>Nueva conversación</h4>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
          <select value={project} onChange={(e) => setProject(e.target.value)} style={{ padding: '8px' }}>
            <option value="">Seleccioná un proyecto…</option>
            {projectOptions.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
          <select value={runtime} onChange={(e) => setRuntime(e.target.value as CliRuntime)} style={{ padding: '8px' }}>
            <option value="claude_code_cli">Claude Code (recomendado)</option>
            <option value="codex_cli">Codex</option>
          </select>
        </div>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Escribí el primer mensaje para el agente DevOps…"
          rows={3}
          style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
        />
        <button
          onClick={() => void handleStart()}
          disabled={!canStart}
          style={{
            padding: '8px 16px',
            backgroundColor: canStart ? '#28a745' : '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: canStart ? 'pointer' : 'not-allowed',
          }}
        >
          Iniciar conversación
        </button>
      </div>

      {/* Aviso GLOBAL de continuidad (operacional, NO gate de flag — C6 v3). */}
      {!resumeEnabled && (
        <div style={{ padding: '8px 12px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', color: '#856404' }}>
          Aviso: sin "Resume de sesión (claude)" activo (Configuración → Arnés, categoría Claude Code CLI), al continuar una conversación terminada el agente arranca sin memoria del hilo.
        </div>
      )}

      {/* Conversaciones */}
      <div style={{ border: '1px solid #dee2e6', borderRadius: '4px', padding: '12px' }}>
        <h4 style={{ marginTop: 0 }}>Conversaciones</h4>
        {conversations.length === 0 ? (
          <p style={{ opacity: 0.7 }}>Todavía no hay conversaciones para este proyecto.</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {conversations.map((item) => (
              <li key={item.conversation_id} style={{ borderBottom: '1px solid #eee', padding: '8px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                  <span>
                    <strong>{item.title}</strong>{' '}
                    <span style={{ opacity: 0.7, fontSize: '0.85em' }}>({item.last_status ?? 'sin ejecuciones'})</span>
                  </span>
                  <span style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => handleOpenConsole(item.last_execution_id)}
                      disabled={item.last_execution_id == null}
                      style={{ padding: '4px 10px' }}
                    >
                      Abrir consola
                    </button>
                  </span>
                </div>
                {/* Continuar: visible solo si no está corriendo (si corre, se responde en el dock). */}
                {item.last_status !== 'running' && (
                  <div style={{ marginTop: '6px' }}>
                    <textarea
                      value={continueDraft[item.conversation_id] ?? ''}
                      onChange={(e) =>
                        setContinueDraft((prev) => ({ ...prev, [item.conversation_id]: e.target.value }))
                      }
                      placeholder="Continuar la conversación…"
                      rows={2}
                      style={{ width: '100%', padding: '6px' }}
                    />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                      <button
                        onClick={() => void handleContinue(item.conversation_id)}
                        disabled={!(continueDraft[item.conversation_id] ?? '').trim()}
                        style={{ padding: '4px 10px' }}
                      >
                        Enviar
                      </button>
                      {item.continuable_with_memory === false && (
                        <span style={{ color: '#856404', fontSize: '0.82em' }}>
                          Continuará sin memoria del hilo (resume off o el último turno no terminó OK).
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

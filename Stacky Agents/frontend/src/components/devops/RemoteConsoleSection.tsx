/**
 * RemoteConsoleSection (Plan 105 F4)
 *
 * Consola remota de prompts por servidor (WinRM) con tabs Conversación/Auditoría.
 * UX-1..UX-5: header profesional, badge persistente + confirmación in-panel,
 * command-cards, chips 1-click, atajos de teclado.
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DevOpsRemoteConsole, type RemoteConsoleConversation } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import styles from './devops.module.css';

export interface RemoteConsoleSectionProps {
  ctx: DevOpsSectionContext;
}

export const RemoteConsoleSection: React.FC<RemoteConsoleSectionProps> = ({ ctx }) => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'conversation' | 'audit'>('conversation');
  const [selectedServer, setSelectedServer] = useState<string | null>(
    ctx.selectedServer?.alias ?? null
  );
  const [selectedConversation, setSelectedConversation] = useState<number | null>(null);
  const [command, setCommand] = useState('');
  const [output, setOutput] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);

  // WinRM check query
  const winrmQuery = useQuery({
    queryKey: ['devops-console-winrm', selectedServer],
    queryFn: () => DevOpsRemoteConsole.checkWinrm(selectedServer!),
    enabled: selectedServer !== null,
    retry: false,
  });

  // Conversations query
  const conversationsQuery = useQuery({
    queryKey: ['devops-console-conversations', selectedServer],
    queryFn: () => DevOpsRemoteConsole.getConversations(selectedServer!),
    enabled: selectedServer !== null && activeTab === 'conversation',
    retry: false,
  });

  // Audit query
  const auditQuery = useQuery({
    queryKey: ['devops-console-audit', selectedServer],
    queryFn: () => DevOpsRemoteConsole.getAudit(selectedServer!),
    enabled: selectedServer !== null && activeTab === 'audit',
    retry: false,
  });

  // Mutations
  const execMutation = useMutation({
    mutationFn: (params: { command: string; conversationId?: number }) =>
      DevOpsRemoteConsole.exec(selectedServer!, params.command, params.conversationId),
    onSuccess: (data, variables) => {
      setOutput((prev) => [
        ...prev,
        { role: 'user', content: variables.command },
        { role: 'assistant', content: `stdout: ${data.stdout}\nstderr: ${data.stderr}` },
      ]);
      if (!variables.conversationId) {
        queryClient.invalidateQueries({ queryKey: ['devops-console-conversations'] });
      }
    },
  });

  const createConvMutation = useMutation({
    mutationFn: (message: string) =>
      DevOpsRemoteConsole.createConversation(selectedServer!, 'default', message),
    onSuccess: (data) => {
      setSelectedConversation(data.conversation_id);
      queryClient.invalidateQueries({ queryKey: ['devops-console-conversations'] });
    },
  });

  const writeModeMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      DevOpsRemoteConsole.setWriteMode(selectedConversation!, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devops-console-conversations'] });
    },
  });

  const conv = conversationsQuery.data?.find((c) => c.id === selectedConversation);

  const handleExec = () => {
    if (!command.trim() || !selectedServer) return;
    execMutation.mutate({ command, conversationId: selectedConversation ?? undefined });
    setCommand('');
  };

  // Command cards UX-3
  const commandCards = [
    { label: 'List processes', cmd: 'Get-Process | Select-Object -First 10' },
    { label: 'Disk usage', cmd: 'Get-PSDrive C | Select-Object Used,Free' },
    { label: 'Event logs', cmd: 'Get-EventLog -LogName Application -Newest 5' },
  ];

  if (!selectedServer && (ctx.servers?.length ?? 0) > 0) {
    return (
      <div className={styles.devopsSection}>
        <p className={styles.text}>Selecciona un servidor para usar la consola remota.</p>
      </div>
    );
  }

  if (!selectedServer) {
    return (
      <div className={styles.devopsSection}>
        <p className={styles.text}>No hay servidores configurados. Ve a la sección Servidores.</p>
      </div>
    );
  }

  return (
    <div className={styles.devopsSection}>
      {/* Header WinRM + badge modo */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>Consola: {selectedServer}</h3>
        {winrmQuery.data?.ok === true ? (
          <span style={{ color: '#28a745', fontSize: '0.9em' }}>✓ WinRM OK</span>
        ) : winrmQuery.data?.ok === false ? (
          <span style={{ color: '#dc3545', fontSize: '0.9em' }}>✗ WinRM error</span>
        ) : null}
      </div>

      {/* Plan 108 F1b (C9 v2): diagnóstico tipificado + remediación copy-paste.
          HITL: Stacky NUNCA ejecuta estos comandos, solo los muestra. */}
      {winrmQuery.data?.ok === false && (
        <details style={{ marginBottom: '16px' }}>
          <summary style={{ cursor: 'pointer' }}>Cómo arreglarlo</summary>
          <div style={{ marginTop: '8px' }}>
            <code>{winrmQuery.data.detail}</code>
          </div>
          {winrmQuery.data.remediation && winrmQuery.data.remediation.length > 0 && (
            <ol style={{ marginTop: '8px' }}>
              {winrmQuery.data.remediation.map((step, i) => (
                <li key={i} style={{ marginBottom: '6px' }}>
                  [{step.where}] {step.label}
                  {step.command != null && (
                    <div>
                      <code>{step.command}</code>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </details>
      )}

      {/* Tabs Conversación/Auditoría */}
      <div style={{ marginBottom: '16px', borderBottom: '1px solid #dee2e6' }}>
        <button
          onClick={() => setActiveTab('conversation')}
          style={{
            padding: '8px 16px',
            border: 'none',
            borderBottom: activeTab === 'conversation' ? '2px solid #007bff' : '2px solid transparent',
            backgroundColor: 'transparent',
            cursor: 'pointer',
          }}
        >
          Conversación
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          style={{
            padding: '8px 16px',
            border: 'none',
            borderBottom: activeTab === 'audit' ? '2px solid #007bff' : '2px solid transparent',
            backgroundColor: 'transparent',
            cursor: 'pointer',
          }}
        >
          Auditoría
        </button>
      </div>

      {activeTab === 'conversation' && (
        <div>
          {/* Selector de conversación */}
          {conversationsQuery.data && conversationsQuery.data.length > 0 && (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '0.9em', color: '#6c757d' }}>Conversación activa:</label>
              <select
                value={selectedConversation ?? ''}
                onChange={(e) => setSelectedConversation(e.target.value ? Number(e.target.value) : null)}
                style={{ marginLeft: '8px', padding: '4px 8px' }}
              >
                <option value="">— nueva —</option>
                {conversationsQuery.data.map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.id} — {c.title.slice(0, 40)}... {c.write_enabled ? '📝' : '👁️'}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Badge write_enabled + toggle */}
          {conv && (
            <div style={{ marginBottom: '16px', padding: '8px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
              <span style={{ fontSize: '0.9em' }}>
                Modo: <strong>{conv.write_enabled ? 'ESCRITURA' : 'SOLO LECTURA'}</strong>
              </span>
              <button
                onClick={() => {
                  if (!conv.write_enabled) {
                    if (confirm('¿Habilitar modo ESCRITURA? Podrás modificar el servidor.')) {
                      writeModeMutation.mutate(true);
                    }
                  } else {
                    writeModeMutation.mutate(false);
                  }
                }}
                disabled={writeModeMutation.isPending}
                style={{ marginLeft: '16px', padding: '4px 8px', fontSize: '0.85em' }}
              >
                {conv.write_enabled ? 'Desactivar escritura' : 'Activar escritura'}
              </button>
            </div>
          )}

          {/* Command cards UX-3 */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '0.9em', color: '#6c757d' }}>Comandos rápidos:</label>
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              {commandCards.map((card) => (
                <button
                  key={card.label}
                  onClick={() => setCommand(card.cmd)}
                  style={{
                    padding: '6px 12px',
                    fontSize: '0.85em',
                    backgroundColor: '#e9ecef',
                    border: '1px solid #ced4da',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  {card.label}
                </button>
              ))}
            </div>
          </div>

          {/* Input de comando */}
          <div style={{ marginBottom: '16px' }}>
            <textarea
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="Escribe un comando PowerShell..."
              style={{
                width: '100%',
                minHeight: '60px',
                padding: '8px',
                fontFamily: 'monospace',
                fontSize: '0.9em',
                border: '1px solid #ced4da',
                borderRadius: '4px',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleExec();
                }
              }}
            />
            <button
              onClick={handleExec}
              disabled={execMutation.isPending || !command.trim()}
              style={{
                marginTop: '8px',
                padding: '8px 16px',
                backgroundColor: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              Ejecutar
            </button>
          </div>

          {/* Output */}
          {output.length > 0 && (
            <div style={{
              padding: '12px',
              backgroundColor: '#f8f9fa',
              border: '1px solid #dee2e6',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '0.85em',
              maxHeight: '300px',
              overflowY: 'auto',
            }}>
              {output.map((line, i) => (
                <div key={i} style={{ marginBottom: '8px' }}>
                  <strong style={{ color: line.role === 'user' ? '#6c757d' : '#007bff' }}>
                    {line.role === 'user' ? '>' : '⊙'}
                  </strong>
                  <span style={{ marginLeft: '8px', whiteSpace: 'pre-wrap' }}>{line.content}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'audit' && (
        <div>
          {auditQuery.data ? (
            <div style={{
              padding: '12px',
              backgroundColor: '#f8f9fa',
              border: '1px solid #dee2e6',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '0.85em',
              maxHeight: '400px',
              overflowY: 'auto',
            }}>
              {auditQuery.data.map((entry, i) => (
                <div key={i} style={{ marginBottom: '8px', borderBottom: '1px solid #e9ecef', paddingBottom: '8px' }}>
                  <div style={{ color: '#6c757d', fontSize: '0.8em' }}>
                    [{entry.timestamp}] {entry.kind}
                  </div>
                  <div style={{ marginTop: '4px' }}>
                    {JSON.stringify(entry, null, 2)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.text}>Cargando auditoría...</p>
          )}
        </div>
      )}
    </div>
  );
};

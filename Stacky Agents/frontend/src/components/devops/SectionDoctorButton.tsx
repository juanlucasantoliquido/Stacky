/**
 * SectionDoctorButton (Plan 104 F3)
 *
 * Botón reutilizable "Doctor" para las secciones del panel DevOps (Pipeline,
 * Environments, Publications). Arma el payload de la sección, invoca al
 * doctor IA (reusa run_agent vía el endpoint F2) y abre la respuesta en el
 * CodexConsoleDock EXISTENTE por execution_id (mismo canal que
 * DevOpsAgentSection.tsx — indexado por execution_id, no por conversación).
 *
 * HITL: el doctor SOLO propone en markdown (instrucción del backend F2);
 * este botón nunca aplica cambios.
 */
import { useState } from 'react';
import { SectionDoctorApi, LocalLlmApi } from '../../api/endpoints';
import { useWorkbench } from '../../store/workbench';
import { buildLocalDoctorBody } from '../../devops/doctorModel';
import styles from './devops.module.css';

type Runtime = "claude_code_cli" | "codex_cli" | "github_copilot";

/**
 * api/client.ts lanza un Error PLANO (`${status} ${statusText}: ${rawBody}`),
 * sin adjuntar el JSON parseado como propiedad (patrón ya confirmado en
 * ProductionFlow.tsx / VariablesSection.tsx — "e?.body?.error" es código
 * muerto). Se parsea el mensaje crudo para mostrar el error real del backend.
 */
function parseDoctorError(e: unknown): string {
  if (!(e instanceof Error)) return 'doctor_failed';
  const idx = e.message.indexOf(': ');
  const rawBody = idx >= 0 ? e.message.slice(idx + 2) : '';
  try {
    const parsed = JSON.parse(rawBody);
    if (typeof parsed?.error === 'string') return parsed.error;
  } catch {
    // no era JSON — usamos el mensaje crudo
  }
  return e.message;
}

export function SectionDoctorButton(props: {
  sectionId: 'pipeline' | 'environments' | 'publications';
  project: string;
  buildPayload: () => Record<string, unknown>;
  disabled?: boolean;
  gateMessage?: string;  // si la flag está OFF, el padre pasa el mensaje y el botón se deshabilita
  localDoctorEnabled?: boolean;  // Plan 127 — health.local_doctor_enabled (conjunción H5)
}) {
  const [runtime, setRuntime] = useState<Runtime>('claude_code_cli');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<number | null>(null);
  // Plan 127 C3 — doctor local: estado propio, panel inline (NO navega a la consola).
  const [localBusy, setLocalBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [localAnalysis, setLocalAnalysis] = useState<string | null>(null);
  // Abre el CodexConsoleDock EXISTENTE por execution_id (igual que
  // DevOpsAgentSection.tsx). La consola se indexa por execution_id, NO por
  // conversación — por eso muestra el markdown del doctor aunque su ticket
  // (ado_id=-3) NO aparezca en la lista de conversaciones del plan 90 (que
  // filtra ado_id=-2).
  const openConsole = useWorkbench((s) => s.setCodexConsoleExecution);

  const noProject = !props.project;  // sin proyecto activo → no dispares el 400 crudo

  const handle = async () => {
    if (props.gateMessage || busy || noProject) return;
    setBusy(true);
    setError(null);
    setExecutionId(null);
    try {
      const res = await SectionDoctorApi.run(props.sectionId, {
        project: props.project,
        runtime,
        payload: props.buildPayload(),
      });
      setExecutionId(res.execution_id);
      openConsole(res.execution_id);   // muestra la respuesta IA de inmediato
    } catch (e: unknown) {
      setError(parseDoctorError(e));
    } finally {
      setBusy(false);
    }
  };

  // Plan 127 C3 — doctor local: gratis, sin egreso, panel inline (no navega a la consola).
  const handleLocal = async () => {
    if (localBusy || noProject) return;
    setLocalBusy(true);
    setLocalError(null);
    setLocalAnalysis(null);
    try {
      const body = buildLocalDoctorBody(props.project, props.buildPayload());
      const res = await LocalLlmApi.sectionDoctorLocal(props.sectionId, body);
      setLocalAnalysis(res.analysis);
    } catch (e: unknown) {
      setLocalError(parseDoctorError(e));
    } finally {
      setLocalBusy(false);
    }
  };

  return (
    <div style={{ marginTop: '8px' }}>
      <select value={runtime} onChange={(e) => setRuntime(e.target.value as Runtime)} disabled={busy}>
        <option value="claude_code_cli">Claude</option>
        <option value="codex_cli">Codex</option>
        <option value="github_copilot">Copilot</option>
      </select>
      <button
        onClick={() => void handle()}
        disabled={busy || !!props.gateMessage || props.disabled || noProject}
        className={styles.btnPrimary}
        style={{ marginLeft: '8px' }}
      >
        {busy ? 'Analizando…' : 'Doctor'}
      </button>
      {noProject && <p className={styles.textMuted}>Elegí un proyecto activo primero.</p>}
      {props.gateMessage && <p className={styles.textMuted}>{props.gateMessage}</p>}
      {error && <p className={styles.textMuted}>No pude lanzar el análisis ({error}).</p>}
      {executionId !== null && (
        <p className={styles.textMuted}>
          Análisis lanzado (execution #{executionId}). La consola con la respuesta IA se abrió abajo.
        </p>
      )}

      {/* Plan 127 C3 — doctor local: solo si el health del panel lo habilita (conjunción H5). */}
      {props.localDoctorEnabled === true && (
        <div style={{ marginTop: '8px' }}>
          <button
            onClick={() => void handleLocal()}
            disabled={localBusy || noProject}
            style={{ marginLeft: '0' }}
          >
            {localBusy ? 'Analizando (puede tardar 1-3 minutos)…' : 'Doctor local (no sale de tu máquina)'}
          </button>
          {localError && <p className={styles.textMuted}>No pude analizar ({localError}).</p>}
          {localAnalysis && (
            <details open style={{ marginTop: '6px' }}>
              <summary className={styles.textMuted} style={{ cursor: 'pointer' }}>
                Análisis local
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '12px', marginTop: '4px' }}>
                {localAnalysis}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

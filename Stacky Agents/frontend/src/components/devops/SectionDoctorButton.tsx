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
import { SectionDoctorApi } from '../../api/endpoints';
import { useWorkbench } from '../../store/workbench';
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
}) {
  const [runtime, setRuntime] = useState<Runtime>('claude_code_cli');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<number | null>(null);
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
    </div>
  );
}

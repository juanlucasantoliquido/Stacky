import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import styles from './DevOpsPage.module.css';
import { buildAwareness } from './devopsShell';
// Plan 103 — badge del último pipeline disparado. Va en el HEADER (no en la barra
// de sub-tabs) a propósito: el header existe con el cockpit ON y OFF.
import {
  useDevopsMonitorStore,
  formatMonitorStatus,
  toneForStatus,
  appliesToProject,
} from '../devops/pipelineMonitor';

const TONO_CLASE = {
  running: styles.pipeBadgeRunning,
  success: styles.pipeBadgeSuccess,
  error: styles.pipeBadgeError,
} as const;

/** Badge solo-lectura. El HITL (disparar/cancelar) vive en Trigger CI, no acá. */
function PipelineBadge({ activeProject }: { activeProject: string }) {
  const last = useDevopsMonitorStore((s) => s.last);
  const clear = useDevopsMonitorStore((s) => s.clear);
  if (!appliesToProject(last, activeProject)) return null;
  const tone = toneForStatus(last!.status);
  return (
    <div className={`${styles.pipeBadge} ${TONO_CLASE[tone]}`} role="status">
      <span>{formatMonitorStatus(last)}</span>
      {last!.webUrl && (
        <a
          className={styles.pipeBadgeLink}
          href={last!.webUrl}
          target="_blank"
          rel="noreferrer"
        >
          ver
        </a>
      )}
      <button
        type="button"
        className={styles.pipeBadgeClose}
        onClick={clear}
        aria-label="Descartar el seguimiento de este pipeline"
        title="Descartar"
      >
        ×
      </button>
    </div>
  );
}

interface ServerOption { alias: string; host: string; }
interface Props {
  health: Record<string, unknown>;
  servers: ServerOption[];
  serversEnabled: boolean;
  selectedAlias: string | null;
  onSelectServer: (alias: string | null) => void;
  /** Plan 239 F4 — línea de estado OPERACIONAL (reemplaza a buildAwareness, que
   *  contaba flags). Ausente ⇒ se conserva la línea del plan 119 tal cual. */
  meta?: { text: string; tone: string }[];
  /** Plan 239 F5 — control "Fijar como inicio". Ausente ⇒ no se muestra. */
  actions?: ReactNode;
  /** Plan 103 — proyecto activo, para no mostrar el badge de OTRO proyecto.
   *  Ausente ⇒ el badge no se muestra (degradación segura). */
  activeProject?: string;
  /** Plan 103 — `health.pipeline_monitor_enabled`. Ausente ⇒ sin badge. */
  monitorEnabled?: boolean;
}

export function DevOpsHeaderV2({
  health, servers, serversEnabled, selectedAlias, onSelectServer, meta, actions,
  activeProject = '', monitorEnabled = false,
}: Props) {
  const segs = meta ?? buildAwareness(health, selectedAlias);
  const showPicker = serversEnabled && servers.length >= 1;
  return (
    <div className={styles.head}>
      <div>
        <h1 className={styles.title}>DevOps</h1>
        <p className={styles.subtitle}>Operación de pipelines, servidores y despliegues.</p>
        <div className={styles.meta}>
          {segs.map((s, i) => (
            <span key={i} className={styles.mk}>
              {i === 0 && (
                <span className={`${styles.dot} ${s.tone === 'ok' ? styles.dotOk : ''}`} />
              )}
              {i > 0 && <span className={styles.sep} aria-hidden>·</span>}
              {s.text}
            </span>
          ))}
        </div>
      </div>
      {monitorEnabled && <PipelineBadge activeProject={activeProject} />}
      {actions}
      {showPicker && (
        <div className={styles.picker}>
          <label className={styles.pickerLabel} htmlFor="devops-server-picker">Servidor activo</label>
          <div className={styles.ctl}>
            <span className={`${styles.dot} ${selectedAlias ? styles.dotOk : ''}`} />
            <select
              id="devops-server-picker"
              className={styles.select}
              value={selectedAlias ?? ''}
              onChange={(e) => onSelectServer(e.target.value || null)}
              aria-label="Servidor activo para las secciones que lo usen"
            >
              <option value="">— ninguno —</option>
              {servers.map((s) => (
                <option key={s.alias} value={s.alias}>{s.alias} · {s.host}</option>
              ))}
            </select>
            <ChevronDown size={14} className={styles.ico} aria-hidden />
          </div>
        </div>
      )}
    </div>
  );
}

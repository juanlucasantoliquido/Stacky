import { ChevronDown } from 'lucide-react';
import styles from './DevOpsPage.module.css';
import { buildAwareness } from './devopsShell';

interface ServerOption { alias: string; host: string; }
interface Props {
  health: Record<string, unknown>;
  servers: ServerOption[];
  serversEnabled: boolean;
  selectedAlias: string | null;
  onSelectServer: (alias: string | null) => void;
}

export function DevOpsHeaderV2({ health, servers, serversEnabled, selectedAlias, onSelectServer }: Props) {
  const segs = buildAwareness(health, selectedAlias);
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

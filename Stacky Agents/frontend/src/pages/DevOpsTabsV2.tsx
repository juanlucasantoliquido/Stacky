import styles from './DevOpsPage.module.css';
import { classifyTab } from './devopsShell';

interface SectionLite { id: string; label: string; healthKey?: string; }
interface Props {
  sections: SectionLite[];
  activeId: string;
  onSelect: (id: string) => void;
  health: Record<string, unknown>;
}

export function DevOpsTabsV2({ sections, activeId, onSelect, health }: Props) {
  const panelOff = health.flag_enabled !== true; // paridad con disabled={!ctx.health.flag_enabled}
  return (
    <nav className={styles.tabs} aria-label="Secciones DevOps">
      {sections.map((s) => {
        const { active, gated } = classifyTab(s, health, activeId);
        const cls = [styles.tab, active ? styles.tabActive : '', gated ? styles.tabOff : '',
                     panelOff ? styles.tabDisabled : ''].filter(Boolean).join(' ');
        return (
          <button
            key={s.id}
            className={cls}
            onClick={() => onSelect(s.id)}   // gated SIGUE clickable (abre el FlagGateBanner en el outlet)
            disabled={panelOff}
            aria-current={active ? 'page' : undefined}
            title={gated ? 'flag off — clic para ver cómo activarla' : undefined}
          >
            {s.label}{gated ? ' · flag off' : ''}
          </button>
        );
      })}
    </nav>
  );
}

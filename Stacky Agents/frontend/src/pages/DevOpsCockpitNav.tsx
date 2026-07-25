/** Plan 239 F4 — navegación de dos niveles del cockpit. Presentación pura.
 *
 *  Usa la primitiva Tabs DOS veces (dos conjuntos independientes, cada uno con su
 *  role="tablist" propio, que es lo que la primitiva ya emite). No reimplementa
 *  ninguna barra a mano. Cero estilos inline: todo sale de DevOpsCockpit.module.css.
 */
import Tabs from '../components/ui/Tabs';
import styles from './DevOpsCockpit.module.css';
import type { DevOpsSection } from './DevOpsPage';
import {
  DEVOPS_SECTION_GROUPS,
  sectionsOfGroup,
  partitionForBar,
  activeGroupOf,
  type DevOpsGroupId,
} from './devopsCockpitShell';

interface Props {
  sections: DevOpsSection[];
  activeId: string;
  onSelect: (id: string) => void;
  health: Record<string, unknown>;
}

export function DevOpsCockpitNav({ sections, activeId, onSelect, health }: Props) {
  const activeGroup = activeGroupOf(sections, activeId);
  const { visibleByGroup, gated } = partitionForBar(sections, health);
  const inGroup = visibleByGroup[activeGroup] ?? [];
  return (
    <>
      <div className={styles.navPrimary}>
        <Tabs
          aria-label="Grupos del panel DevOps"
          size="md"
          items={DEVOPS_SECTION_GROUPS.map((g) => ({ id: g.id, label: g.label }))}
          activeId={activeGroup}
          onChange={(gid) => {
            // Al cambiar de grupo se abre su PRIMERA sección visible; si el grupo
            // no tiene ninguna visible, se abre la primera gateada (para que el
            // operador llegue al FlagGateBanner y sepa cómo prenderla).
            const g = gid as DevOpsGroupId;
            const first = visibleByGroup[g]?.[0] ?? sectionsOfGroup(sections, g)[0];
            if (first) onSelect(first.id);
          }}
        />
        {gated.length > 0 && (
          <details className={styles.disabledDisclosure}>
            <summary>{`Deshabilitadas (${gated.length})`}</summary>
            {gated.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => onSelect(s.id)}
                title="Flag apagada — clic para ver cómo activarla"
              >
                {s.label}
              </button>
            ))}
          </details>
        )}
      </div>
      {inGroup.length > 1 && (
        <div className={styles.navSecondary}>
          <Tabs
            aria-label={`Secciones de ${activeGroup}`}
            size="sm"
            items={inGroup.map((s) => ({ id: s.id, label: s.label }))}
            activeId={activeId}
            onChange={onSelect}
          />
        </div>
      )}
    </>
  );
}

export default DevOpsCockpitNav;

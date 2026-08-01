import type { ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { IconButton } from "../ui";
import { ICON_BY_NAME } from "./shellIcons";
import {
  TAB_META, orderedVisibleGroups, type ShellTab,
} from "./shellNav";
// Plan 282 F4/F7 — el rótulo y la disponibilidad del tab siguen al tracker.
// `TAB_META` NO se toca: lo congelan 4 suites y lo consume App.tsx.
import { labelDeTab } from "../../lib/trackerLabels";
import { tabDisponible, motivoNoDisponible } from "../../lib/tabsPorTracker";
import styles from "./AppSidebar.module.css";

export interface AppSidebarProps {
  activeTab: ShellTab;
  onSelect: (tab: ShellTab) => void;
  visibleTabs: ReadonlySet<ShellTab>;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  badges?: Partial<Record<ShellTab, ReactNode>>;
  /** Plan 282 F4/F7 — tracker del proyecto activo. OPCIONAL: sin él, los
   *  rótulos caen al label estático y todos los tabs quedan habilitados
   *  (falla abierto), que es el comportamiento previo al plan. */
  trackerType?: string | null;
}

export default function AppSidebar({
  activeTab, onSelect, visibleTabs, collapsed, onToggleCollapsed, badges,
  trackerType = null,
}: AppSidebarProps) {
  const groups = orderedVisibleGroups(visibleTabs);
  return (
    <aside
      className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Navegación principal"
    >
      <nav className={styles.groups} data-tour="nav">
        {groups.map((g) => (
          <div key={g.id} className={styles.group}>
            <div className={styles.groupLabel}>{g.label}</div>
            {g.tabs.map((t) => {
              const meta = TAB_META[t];
              const Icon = ICON_BY_NAME[meta.iconName];
              const isActive = activeTab === t;
              const badge = badges?.[t];
              // Plan 282 F4 — el rótulo se rutea acá, en el render, sin tocar
              // TAB_META (que sigue siendo la fuente del label estático).
              const rotulo = labelDeTab(t, meta.label, trackerType);
              // Plan 282 F7 — un tab ADO-only en un proyecto GitLab se muestra
              // DESHABILITADO con motivo. Ocultarlo mataría el deep link.
              const habilitado = tabDisponible(t, trackerType);
              const motivo = motivoNoDisponible(t, trackerType);
              return (
                <button
                  key={t}
                  type="button"
                  className={`${styles.item} ${isActive ? styles.active : ""}`}
                  aria-current={isActive ? "page" : undefined}
                  title={motivo || rotulo}
                  disabled={!habilitado}
                  onClick={() => onSelect(t)}
                >
                  <span className={styles.itemIcon} aria-hidden="true">
                    {Icon ? <Icon size={18} strokeWidth={2} /> : null}
                  </span>
                  <span className={styles.itemLabel}>{rotulo}</span>
                  {badge != null && <span className={styles.itemBadge}>{badge}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <div className={styles.footer}>
        <IconButton
          label={collapsed ? "Expandir menú" : "Plegar menú"}
          icon={collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          size="sm"
          onClick={onToggleCollapsed}
        />
      </div>
    </aside>
  );
}

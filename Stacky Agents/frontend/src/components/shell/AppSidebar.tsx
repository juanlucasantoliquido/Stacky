import type { ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { IconButton } from "../ui";
import { ICON_BY_NAME } from "./shellIcons";
import {
  TAB_META, orderedVisibleGroups, type ShellTab,
} from "./shellNav";
import styles from "./AppSidebar.module.css";

export interface AppSidebarProps {
  activeTab: ShellTab;
  onSelect: (tab: ShellTab) => void;
  visibleTabs: ReadonlySet<ShellTab>;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  badges?: Partial<Record<ShellTab, ReactNode>>;
}

export default function AppSidebar({
  activeTab, onSelect, visibleTabs, collapsed, onToggleCollapsed, badges,
}: AppSidebarProps) {
  const groups = orderedVisibleGroups(visibleTabs);
  return (
    <aside
      className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Navegación principal"
    >
      <nav className={styles.groups}>
        {groups.map((g) => (
          <div key={g.id} className={styles.group}>
            <div className={styles.groupLabel}>{g.label}</div>
            {g.tabs.map((t) => {
              const meta = TAB_META[t];
              const Icon = ICON_BY_NAME[meta.iconName];
              const isActive = activeTab === t;
              const badge = badges?.[t];
              return (
                <button
                  key={t}
                  type="button"
                  className={`${styles.item} ${isActive ? styles.active : ""}`}
                  aria-current={isActive ? "page" : undefined}
                  title={meta.label}
                  onClick={() => onSelect(t)}
                >
                  <span className={styles.itemIcon} aria-hidden="true">
                    {Icon ? <Icon size={18} strokeWidth={2} /> : null}
                  </span>
                  <span className={styles.itemLabel}>{meta.label}</span>
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

import { ReactNode } from "react";
import styles from "./Tabs.module.css";

export type TabsSize = "sm" | "md";

export interface TabItem {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Default "md". */
  size?: TabsSize;
  "aria-label"?: string;
}

export function tabPartKeys(active: boolean, size: TabsSize): string[] {
  const keys = ["tab", size];
  if (active) keys.push("active");
  return keys;
}

export default function Tabs({ items, activeId, onChange, size, ...rest }: TabsProps) {
  return (
    <div className={styles.tabs} role="tablist" aria-label={rest["aria-label"]}>
      {items.map((item) => {
        const keys = tabPartKeys(item.id === activeId, size ?? "md");
        const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === activeId}
            className={cls}
            onClick={() => onChange(item.id)}
          >
            {item.icon}
            {item.label}
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}

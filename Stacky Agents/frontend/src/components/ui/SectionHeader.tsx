import { ReactNode } from "react";
import styles from "./SectionHeader.module.css";

export interface SectionHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export default function SectionHeader({ title, subtitle, actions }: SectionHeaderProps) {
  return (
    <div className={styles.root}>
      <div className={styles.titles}>
        <h3 className={styles.title}>{title}</h3>
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}

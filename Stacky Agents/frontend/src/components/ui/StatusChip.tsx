import { ReactNode } from "react";
import styles from "./StatusChip.module.css";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";
export type ChipSize = "sm" | "md";

export interface StatusChipProps {
  tone: StatusTone;
  children: ReactNode;
  icon?: ReactNode;
  /** Default "sm". */
  size?: ChipSize;
  title?: string;
}

export function chipPartKeys(tone: StatusTone, size: ChipSize): string[] {
  return ["chip", tone, size];
}

export default function StatusChip({ tone, children, icon, size, title }: StatusChipProps) {
  const cls = chipPartKeys(tone, size ?? "sm").map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <span className={cls} title={title}>
      {icon}
      {children}
    </span>
  );
}

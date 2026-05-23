import { ReactNode } from "react";
import styles from "./EmptyState.module.css";

export type EmptyVariant =
  | "executions"
  | "packs"
  | "tickets"
  | "agents"
  | "history"
  | "generic";

interface Props {
  variant?: EmptyVariant;
  title?: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: ReactNode;
}

const VARIANT_PRESETS: Record<EmptyVariant, {
  icon: string;
  title: string;
  message: string;
  actionLabel?: string;
}> = {
  executions: {
    icon: "⚡",
    title: "Acá vas a ver tus ejecuciones",
    message: "Cada vez que corras un agente queda registro con su output. Probá uno desde Mi Equipo.",
    actionLabel: "Correr mi primer agente",
  },
  packs: {
    icon: "📦",
    title: "Todavía no corriste packs",
    message: "Un pack es una receta: corre 4 agentes en orden con un click. Empezá con el Pack Desarrollo.",
    actionLabel: "Ver packs",
  },
  tickets: {
    icon: "🎫",
    title: "Sin tickets visibles",
    message: "Conectá un tracker (ADO, Jira, Mantis) o cambiá de proyecto para ver tickets.",
    actionLabel: "Configurar proyecto",
  },
  agents: {
    icon: "🤖",
    title: "Tu equipo está vacío",
    message: "Agregá tu primer agente para empezar a asignar tickets.",
    actionLabel: "Agregar agente",
  },
  history: {
    icon: "📜",
    title: "Sin historial todavía",
    message: "Cuando corras agentes, el historial va a aparecer acá.",
  },
  generic: {
    icon: "✨",
    title: "Nada por acá",
    message: "Cuando haya información para mostrar, va a aparecer en este lugar.",
  },
};

export default function EmptyState({
  variant = "generic",
  title,
  message,
  actionLabel,
  onAction,
  icon,
}: Props) {
  const preset = VARIANT_PRESETS[variant];
  const finalTitle = title ?? preset.title;
  const finalMessage = message ?? preset.message;
  const finalAction = actionLabel ?? preset.actionLabel;

  return (
    <div className={styles.root}>
      <div className={styles.icon} aria-hidden="true">
        {icon ?? preset.icon}
      </div>
      <h3 className={styles.title}>{finalTitle}</h3>
      <p className={styles.message}>{finalMessage}</p>
      {finalAction && onAction ? (
        <button className={styles.action} onClick={onAction}>
          ▶ {finalAction}
        </button>
      ) : null}
    </div>
  );
}

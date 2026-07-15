import { ReactNode } from "react";
import { Button } from "./ui";
import styles from "./EmptyState.module.css";

export type EmptyVariant =
  | "executions"
  | "packs"
  | "tickets"
  | "agents"
  | "history"
  | "review"
  | "docs"
  | "no_project"
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
  review: {
    icon: "✅",
    title: "Bandeja al día",
    message: "No hay ejecuciones que requieran tu revisión. Cuando un agente termine con dudas o error, va a aparecer acá.",
  },
  docs: {
    icon: "📚",
    title: "Sin documentación indexada",
    message: "Todavía no hay documentos para explorar. Indexá el proyecto para ver el grafo y buscar contenido.",
    actionLabel: "Indexar ahora",
  },
  no_project: {
    icon: "📂",
    title: "Ningún proyecto activo",
    message: "Seleccioná un proyecto desde la barra superior para ver su equipo.",
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
        <Button variant="primary" size="md" onClick={onAction}>{finalAction}</Button>
      ) : null}
    </div>
  );
}

export function emptyStatePreset(variant: EmptyVariant) {
  return VARIANT_PRESETS[variant];
}

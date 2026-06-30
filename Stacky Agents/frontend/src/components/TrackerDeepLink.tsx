/**
 * TrackerDeepLink — componente React provider-agnóstico (Plan 75 F4).
 *
 * Renderiza un deep link a un recurso externo (ADO, GitLab, etc.) con
 * target="_blank" rel="noopener noreferrer". Si la URL es null, vacía o undefined,
 * renderiza el label como <span> sin link (el backend devuelve null cuando el
 * flag STACKY_GITLAB_DEEP_LINKS_ENABLED=false o el proyecto no es gitlab).
 *
 * El frontend NO compone URLs; solo renderiza strings que el backend le pasa.
 */
import type { ReactNode } from "react";

interface TrackerDeepLinkProps {
  url: string | null | undefined;
  label: ReactNode;
  className?: string;
}

export function TrackerDeepLink({ url, label, className }: TrackerDeepLinkProps) {
  if (!url) return <span className={className}>{label}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}>
      {label}
    </a>
  );
}

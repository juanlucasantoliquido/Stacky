/*
 * N3 — TicketFingerprint
 * Muestra el Pre-Analysis Fingerprint (TPAF) de un ticket.
 * Se carga automáticamente al seleccionar un ticket, antes de elegir agente.
 * Informa al operador: tipo de cambio, dominio, complejidad, pack sugerido.
 */
import { useQuery } from "@tanstack/react-query";
import { Tickets } from "../api/endpoints";
import type { TicketFingerprint as TF } from "../types";
import styles from "./TicketFingerprint.module.css";

interface Props {
  ticketId: number;
  onSuggestPack?: (packId: string) => void;
}

const COMPLEXITY_LABEL: Record<string, string> = {
  S: "Simple",
  M: "Mediana",
  L: "Compleja",
  XL: "Muy compleja",
};

const CHANGE_TYPE_LABEL: Record<string, string> = {
  feature: "Nueva funcionalidad",
  bug: "Bug / Defecto",
  refactor: "Refactor",
  config: "Configuración",
  unknown: "No determinado",
};

const CHANGE_TYPE_ICON: Record<string, string> = {
  feature: "✦",
  bug: "⚡",
  refactor: "↺",
  config: "⚙",
  unknown: "?",
};

export default function TicketFingerprint({ ticketId, onSuggestPack }: Props) {
  const { data, isLoading, isError } = useQuery<TF>({
    queryKey: ["fingerprint", ticketId],
    queryFn: () => Tickets.fingerprint(ticketId),
    staleTime: 5 * 60 * 1000,   // 5 min — no re-fetches frecuentes
    retry: false,
  });

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <span className={styles.dot} />
        <span>Analizando ticket…</span>
      </div>
    );
  }

  if (isError || !data) return null;

  const complexityTier =
    data.complexity === "S" || data.complexity === "M" ? "low" : "high";

  return (
    <div className={styles.panel}>
      <div className={styles.row}>
        <Chip
          icon={CHANGE_TYPE_ICON[data.change_type] ?? "?"}
          label={CHANGE_TYPE_LABEL[data.change_type] ?? data.change_type}
          title="Tipo de cambio detectado"
        />
        <Chip
          icon="⊞"
          label={data.domain.join(", ")}
          title={`Dominios detectados (confianza ${Math.round(data.domain_confidence * 100)}%)`}
          muted={data.domain_confidence < 0.3}
        />
        <Chip
          icon="≈"
          label={`${data.complexity} — ${COMPLEXITY_LABEL[data.complexity]}`}
          title="Complejidad estimada"
          tier={complexityTier}
        />
      </div>

      {data.suggested_pack && (
        <div className={styles.packRow}>
          <span className={styles.packLabel}>Pack sugerido:</span>
          <button
            className={styles.packBtn}
            onClick={() => onSuggestPack?.(data.suggested_pack)}
            title="Iniciar este pack"
          >
            ▶ {data.suggested_pack}
          </button>
          {data.keywords_detected.length > 0 && (
            <span className={styles.keywords} title="Keywords detectados">
              {data.keywords_detected.slice(0, 5).join(" · ")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Chip({
  icon,
  label,
  title,
  muted,
  tier,
}: {
  icon: string;
  label: string;
  title: string;
  muted?: boolean;
  tier?: "low" | "high";
}) {
  return (
    <span
      className={styles.chip}
      title={title}
      data-muted={muted ? "true" : undefined}
      data-tier={tier}
    >
      <span className={styles.chipIcon}>{icon}</span>
      <span>{label}</span>
    </span>
  );
}

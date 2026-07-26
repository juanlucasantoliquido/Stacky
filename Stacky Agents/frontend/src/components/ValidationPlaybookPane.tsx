import styles from "./ValidationPlaybookPane.module.css";

/**
 * Plan 209 F4 — "Cómo validar esto (como usuario del sistema RS)".
 *
 * Renderiza el objeto canónico que el backend persiste en
 * `execution.metadata.validation_playbook`. Se dibuja como JSX (nunca
 * `dangerouslySetInnerHTML`): el HTML del agente no se inyecta en la UI.
 */

export const VALIDATION_SECTION_TITLE =
  "Cómo validar esto (como usuario del sistema RS)";

export const VALIDATION_DEGRADED_MESSAGE =
  "Estos pasos no pudieron verificarse contra la documentación del producto. " +
  "Confirmá con un referente de RS antes de usarlos.";

export type ValidationPlaybookStatus =
  | "agent_provided"
  | "enriched"
  | "degraded"
  | "disabled";

export interface ValidationPlaybookStep {
  n: number;
  action: string;
  expected_result: string;
  source: string;
}

export interface ValidationPlaybook {
  status: ValidationPlaybookStatus;
  steps: ValidationPlaybookStep[];
  sources: string[];
  confidence: number;
  degraded_reason: string | null;
}

/** Lee el playbook de la metadata de una ejecución. Devuelve null si no aplica. */
export function readValidationPlaybook(
  metadata: Record<string, unknown> | undefined | null,
): ValidationPlaybook | null {
  const raw = metadata?.validation_playbook;
  if (!raw || typeof raw !== "object") return null;
  const pb = raw as Partial<ValidationPlaybook>;
  if (!pb.status || pb.status === "disabled") return null;
  return {
    status: pb.status,
    steps: Array.isArray(pb.steps) ? pb.steps : [],
    sources: Array.isArray(pb.sources) ? pb.sources : [],
    confidence: typeof pb.confidence === "number" ? pb.confidence : 0,
    degraded_reason: pb.degraded_reason ?? null,
  };
}

export default function ValidationPlaybookPane({
  playbook,
}: {
  playbook: ValidationPlaybook;
}) {
  if (playbook.status === "disabled") return null;

  const degraded = playbook.status === "degraded";
  const pct = Math.round(Math.max(0, Math.min(1, playbook.confidence)) * 100);

  return (
    <section className={styles.pane} aria-label={VALIDATION_SECTION_TITLE}>
      <div className={styles.head}>
        <span className={styles.icon} aria-hidden="true">
          🧭
        </span>
        <h4 className={styles.title}>{VALIDATION_SECTION_TITLE}</h4>
        {!degraded && (
          <span className={styles.confidence} title="Qué tan sólida es la base documental">
            confianza {pct}%
          </span>
        )}
      </div>

      {degraded ? (
        <p className={styles.degraded}>{VALIDATION_DEGRADED_MESSAGE}</p>
      ) : playbook.steps.length === 0 ? (
        <p className={styles.empty}>Sin pasos de validación disponibles.</p>
      ) : (
        <>
          <p className={styles.intro}>
            Pasos que podés seguir vos mismo en el producto para comprobar este
            cambio. Cada uno cita la fuente en la que está apoyado.
          </p>
          <ol className={styles.steps}>
            {playbook.steps.map((step) => (
              <li key={step.n} className={styles.step}>
                {step.action}
                {step.expected_result && (
                  <span className={styles.expected}>
                    Resultado esperado: {step.expected_result}
                  </span>
                )}
                {step.source && (
                  <span className={styles.sourceChip}>{step.source}</span>
                )}
              </li>
            ))}
          </ol>
          {playbook.sources.length > 0 && (
            <p className={styles.footer}>Fuentes: {playbook.sources.join(", ")}</p>
          )}
        </>
      )}
    </section>
  );
}

/**
 * EgressSentinelBlock.tsx — Plan 121 F5.
 *
 * Bloque presentacional puro: hallazgos del centinela local de egreso (secretos/PII
 * semántico). Sin datos → no renderiza nada (cero ruido si la feature está OFF, KPI-6).
 * Advisory puro: solo muestra, nunca bloquea ni decide por el operador (HITL).
 */
import styles from "./EgressSentinelBlock.module.css";

export interface EgressSentinelFinding {
  data_class: string;
  severity: string;
  excerpt_masked: string;
  rationale: string;
}

export interface EgressSentinelData {
  status: string;
  findings: EgressSentinelFinding[];
  deterministic_classes: string[];
}

interface Props {
  sentinel?: EgressSentinelData | null;
}

const SEVERITY_CLASS: Record<string, string> = {
  critical: styles.severityCritical,
  warning: styles.severityWarning,
  info: styles.severityInfo,
};

export default function EgressSentinelBlock({ sentinel }: Props) {
  if (!sentinel) return null;

  const hasFindings = (sentinel.findings?.length ?? 0) > 0;
  const hasDeterministic = (sentinel.deterministic_classes?.length ?? 0) > 0;
  const isClean = sentinel.status === "clean" && !hasDeterministic;

  return (
    <section className={styles.block}>
      <h4 className={styles.title}>Centinela de egreso (IA local)</h4>

      {isClean && !hasFindings && (
        <span className={styles.cleanChip}>Egreso: limpio</span>
      )}

      {(hasFindings || hasDeterministic) && (
        <>
          <span className={styles.alertChip}>Posible fuga en el prompt</span>
          {hasDeterministic && (
            <div className={styles.deterministic}>
              Patrones detectados: {sentinel.deterministic_classes.join(", ")}
            </div>
          )}
          {hasFindings && (
            <ul className={styles.findings}>
              {sentinel.findings.map((f, i) => (
                <li key={i} className={styles.finding}>
                  <span className={`${styles.severityBadge} ${SEVERITY_CLASS[f.severity] ?? styles.severityInfo}`}>
                    {f.severity}
                  </span>
                  <span className={styles.dataClass}>{f.data_class}</span>
                  <code className={styles.excerpt}>{f.excerpt_masked}</code>
                  {f.rationale && <span className={styles.rationale}>{f.rationale}</span>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <p className={styles.disclaimer}>
        Detectado por la IA local. El contenido nunca salió de esta máquina para este análisis.
      </p>
    </section>
  );
}

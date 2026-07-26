import { useState } from "react";

import { QaUat } from "../api/endpoints";
import { Button, StatusChip } from "./ui";
import {
  candidateLabel,
  candidateTone,
  categoryLabel,
  readQaUatCandidate,
  readQaUatVerdict,
  verdictTone,
  weaknessNote,
} from "./qaUatVerdictModel";
import styles from "./QaUatVerdictPane.module.css";

/**
 * Plan 214 F4 — El resultado de la validación E2E, con su nivel de confianza real.
 *
 * Data-driven: si la metadata no trae ni veredicto ni candidato, no renderiza nada
 * (backward-compatible con toda ejecución previa).
 */
export default function QaUatVerdictPane({
  agentType,
  metadata,
}: {
  agentType: string | undefined;
  metadata: Record<string, unknown> | undefined | null;
}) {
  const [lanzando, setLanzando] = useState(false);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const verdict = agentType === "qa-uat" ? readQaUatVerdict(metadata) : null;
  const candidate = agentType === "developer" ? readQaUatCandidate(metadata) : null;

  if (!verdict && !candidate) return null;

  if (verdict) {
    const nota = weaknessNote(verdict.weak_assertions_count, verdict.verdict);
    return (
      <section className={styles.pane}>
        <div className={styles.head}>
          <h4 className={styles.title}>Validación E2E</h4>
          <StatusChip tone={verdictTone(verdict.verdict)}>{verdict.verdict}</StatusChip>
        </div>
        <dl className={styles.rows}>
          <dt className={styles.label}>Categoría</dt>
          <dd className={styles.value}>{categoryLabel(verdict.verdict_category)}</dd>
          {verdict.verdict_reason && (
            <>
              <dt className={styles.label}>Motivo</dt>
              <dd className={styles.value}>{verdict.verdict_reason}</dd>
            </>
          )}
          {verdict.nav_deviations != null && (
            <>
              <dt className={styles.label}>Desvíos de navegación</dt>
              <dd className={styles.value}>{verdict.nav_deviations}</dd>
            </>
          )}
          {verdict.replan_rounds != null && (
            <>
              <dt className={styles.label}>Replanes</dt>
              <dd className={styles.value}>{verdict.replan_rounds}</dd>
            </>
          )}
          {verdict.playbooks_used?.length ? (
            <>
              <dt className={styles.label}>Playbooks usados</dt>
              <dd className={styles.value}>{verdict.playbooks_used.join(", ")}</dd>
            </>
          ) : null}
        </dl>
        {nota && <p className={styles.weak}>{nota}</p>}
      </section>
    );
  }

  const etiqueta = candidateLabel(candidate ?? undefined);
  if (!etiqueta) return null;

  const lanzar = () => {
    if (!candidate?.ado_id) return;
    setLanzando(true);
    setError(null);
    void QaUat.run({ ticket_id: candidate.ado_id, mode: "dry-run" })
      .then((res) => setStreamUrl(res.stream_url ?? null))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "No se pudo lanzar la validación"),
      )
      .finally(() => setLanzando(false));
  };

  return (
    <section className={styles.pane}>
      <div className={styles.head}>
        <h4 className={styles.title}>Validación E2E</h4>
        <StatusChip tone={candidateTone(candidate ?? undefined)}>{etiqueta}</StatusChip>
      </div>
      {candidate?.status === "pending" && (
        <div className={styles.actions}>
          <Button onClick={lanzar} disabled={lanzando || !candidate.ado_id}>
            {lanzando ? "Lanzando…" : "Validar E2E (dry-run)"}
          </Button>
          <p className={styles.hint}>
            Corre el pipeline sin publicar nada; podés seguir el log en vivo.
          </p>
        </div>
      )}
      {streamUrl && (
        <p className={styles.hint}>
          <a href={streamUrl} target="_blank" rel="noreferrer">
            Ver log en vivo
          </a>
        </p>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </section>
  );
}

import React from "react";

import {
  gapHeadline,
  phaseRows,
  profileErrorCopy,
  summaryRows,
  type PipelineProfileDto,
  type ProfileRow,
} from "../../devops/pipelineProfileModel";
import styles from "./PipelineProfileCard.module.css";

/**
 * Plan 247 F5 — ficha del perfil: qué es, qué hace y con qué está hecha la pipeline.
 *
 * Presentacional PURO: no hace fetch. Toda la lógica vive en el modelo puro
 * `pipelineProfileModel.ts` (con tests). Este archivo sólo pinta, y el estilado
 * sale entero del .module.css con tokens del theme.
 */

export interface PipelineProfileCardProps {
  profile: PipelineProfileDto | null;
  loading: boolean;
  error?: string | null;
  /** undefined ⇒ no se muestra el botón de redactar (HITL: un click, una pipeline). */
  onNarrate?: () => void;
}

const TONE_CLASS: Record<ProfileRow["tone"], string> = {
  ok: styles.toneOk,
  gap: styles.toneGap,
  unknown: styles.toneUnknown,
};

function Row({ row }: { row: ProfileRow }) {
  return (
    <>
      <span className={styles.rowLabel}>{row.label}</span>
      <span className={`${styles.rowValue} ${TONE_CLASS[row.tone]}`} title={row.evidence.join(" | ")}>
        {row.text}
      </span>
    </>
  );
}

export const PipelineProfileCard: React.FC<PipelineProfileCardProps> = ({
  profile,
  loading,
  error,
  onNarrate,
}) => {
  if (error) {
    return (
      <div className={styles.card}>
        <span className={styles.error}>{profileErrorCopy(error)}</span>
      </div>
    );
  }
  if (loading) {
    return (
      <div className={styles.card}>
        <span className={styles.loading}>Perfilando la pipeline…</span>
      </div>
    );
  }
  if (!profile) return null;
  if (profile.parse_error) {
    return (
      <div className={styles.card}>
        <span className={styles.error}>{profile.parse_error}</span>
      </div>
    );
  }

  const gap = gapHeadline(profile);

  return (
    <div className={styles.card}>
      <div className={styles.headline}>{profile.purpose}</div>
      <div className={styles.badges}>
        <span className={styles.badge}>
          {profile.purpose_source === "llm" ? "IA" : "plantilla"}
        </span>
        {profile.not_understood.map((c) => (
          <span key={c} className={styles.badge}>
            no interpretado: {c}
          </span>
        ))}
        {gap ? <span className={styles.gap}>{gap}</span> : null}
      </div>

      <div className={styles.grid}>
        {summaryRows(profile).map((row) => (
          <Row key={row.label} row={row} />
        ))}
        {phaseRows(profile).map((row) => (
          <Row key={`fase-${row.label}`} row={row} />
        ))}
      </div>

      {onNarrate ? (
        <div className={styles.actions}>
          <button type="button" onClick={onNarrate}>
            Redactar con IA
          </button>
        </div>
      ) : null}
    </div>
  );
};

export default PipelineProfileCard;

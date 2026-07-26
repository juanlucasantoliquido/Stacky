import React, { useMemo, useState } from "react";

import { PipelineAudit } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, SectionHeader } from "../ui";
import {
  AUDIT_SEVERITIES,
  auditSummary,
  canSuppress,
  familyOf,
  groupAuditFindings,
  type AuditFinding,
  type AuditReport,
  type AuditSeverity,
} from "../../devops/pipelineAuditModel";
import styles from "./PipelineAuditPanel.module.css";

/**
 * Plan 248 F6 — auditoría de una pipeline que YA existe.
 *
 * READ-ONLY: muestra la remediación como TEXTO y no ofrece ningún botón de "arreglar"
 * (aplicar el fix es el plan 250). El único botón que escribe algo es "Suprimir", y
 * está deshabilitado hasta que el motivo tenga texto.
 *
 * Toda la lógica vive en el modelo puro `pipelineAuditModel.ts` (con tests); acá sólo
 * se pinta, y el estilado sale entero del .module.css.
 */

const TONE_CLASS: Record<string, string> = {
  ok: styles.toneOk,
  warn: styles.toneWarn,
  bad: styles.toneBad,
  none: styles.toneNone,
};

const SEVERITY_TITLE: Record<AuditSeverity, string> = {
  error: "Riesgos graves",
  warning: "Avisos",
  info: "Recomendaciones",
};

const PIPELINE_KEY_DEMO = "panel";

export function PipelineAuditPanel({ ctx }: { ctx: DevOpsSectionContext }) {
  void ctx;
  const [yamlText, setYamlText] = useState("");
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const grouped = useMemo(() => groupAuditFindings(report?.findings ?? []), [report]);
  const summary = auditSummary(report);

  const scan = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await PipelineAudit.scan({
        yaml: yamlText,
        provider: "ado",
        pipeline_key: PIPELINE_KEY_DEMO,
      });
      setReport(r);
    } catch (e: unknown) {
      setReport(null);
      setError(e instanceof Error ? e.message : "no se pudo auditar");
    } finally {
      setLoading(false);
    }
  };

  const suppress = async (f: AuditFinding) => {
    const reason = reasons[f.evidence_fingerprint] || "";
    if (!canSuppress(f, reason)) return;
    try {
      await PipelineAudit.suppress({
        pipeline_key: PIPELINE_KEY_DEMO,
        code: f.code,
        location: f.location,
        evidence_fingerprint: f.evidence_fingerprint,
        reason,
      });
      await scan();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "no se pudo suprimir");
    }
  };

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Auditoria de pipelines"
        subtitle="Riesgos de seguridad y recomendaciones sobre una pipeline que ya existe. Solo lectura."
      />

      <div className={styles.toolbar}>
        <textarea
          className={styles.editor}
          placeholder="Pega aca el YAML de la pipeline"
          value={yamlText}
          onChange={(e) => setYamlText(e.target.value)}
          aria-label="YAML de la pipeline"
        />
        <Button variant="secondary" onClick={() => void scan()} disabled={loading || !yamlText.trim()}>
          {loading ? "Auditando…" : "Auditar"}
        </Button>
      </div>

      <span className={`${styles.summary} ${TONE_CLASS[summary.tone]}`}>{summary.text}</span>
      {error ? <span className={styles.error}>{error}</span> : null}

      {report && report.undetermined > 0 ? (
        <div className={styles.notes}>
          <strong>{`La auditoria no pudo evaluar ${report.undetermined} punto(s)`}</strong>
          {report.undetermined_notes.map((n) => (
            <span key={n}>{n}</span>
          ))}
        </div>
      ) : null}

      {report && report.findings.length === 0 ? (
        <span className={styles.empty}>Sin hallazgos para esta pipeline.</span>
      ) : null}

      {AUDIT_SEVERITIES.filter((sev) => grouped[sev].length > 0).map((sev) => (
        <div key={sev} className={styles.group}>
          <span className={styles.groupTitle}>
            {SEVERITY_TITLE[sev]} ({grouped[sev].length})
          </span>
          {grouped[sev].map((f) => (
            <div key={f.evidence_fingerprint} className={styles.finding}>
              <div className={styles.findingHead}>
                <span className={styles.code}>{f.code}</span>
                <span>{f.message}</span>
                <span className={styles.anchor}>
                  {f.line ? `linea ${f.line}` : f.location} · {familyOf(f.code)}
                </span>
              </div>
              <span className={styles.remediation}>{f.remediation}</span>
              <div className={styles.suppressRow}>
                <input
                  className={styles.reason}
                  placeholder="Motivo para archivar este hallazgo"
                  value={reasons[f.evidence_fingerprint] || ""}
                  onChange={(e) =>
                    setReasons((prev) => ({ ...prev, [f.evidence_fingerprint]: e.target.value }))
                  }
                  aria-label={`Motivo para archivar ${f.code}`}
                />
                <Button
                  variant="secondary"
                  onClick={() => void suppress(f)}
                  disabled={!canSuppress(f, reasons[f.evidence_fingerprint] || "")}
                >
                  Suprimir
                </Button>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default PipelineAuditPanel;

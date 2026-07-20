// Plan 180 F5 — Panel de cobertura del repo: "N de M items del diff tienen script
// ticketeado candidato". Autocontenido: montaje de 1 linea en DbComparePage.
//
// HITL absoluto: SOLO informa. Cada candidato es una PISTA (ticket + ruta +
// matched_by), nunca un veredicto. No excluye items, no edita ni ejecuta scripts.
//
// Sin RTL/jsdom (gap estructural del repo): la logica pura vive en
// repoCoverageLogic.ts (testeada con vitest). Este archivo es JSX + fetch,
// verificado con tsc --noEmit. CERO estilos inline (uiDebtRatchet): clases en
// dbcompare.module.css.
import { useCallback, useEffect, useState } from "react";
import { DbCompareRepo } from "../../api/endpoints";
import type { RepoCoverage } from "./repoCoverageTypes";
import { coverageSummary, severityOrder } from "./repoCoverageLogic";
import { copyText } from "../../services/copyService";
import styles from "./dbcompare.module.css";

interface Props {
  runId: string;
}

export function RepoCoveragePanel({ runId }: Props) {
  const [coverage, setCoverage] = useState<RepoCoverage | null>(null);
  const [workspace, setWorkspace] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    DbCompareRepo.runCoverage(runId)
      .then((r) => {
        setCoverage(r.coverage);
        setWorkspace(r.workspace);
      })
      .catch(() => {
        // 403 (flag OFF) o red: el panel se auto-oculta (KPI-1). Sin ruido.
        setCoverage(null);
        setWorkspace(null);
      });
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  const rescan = useCallback(() => {
    setRefreshing(true);
    DbCompareRepo.refresh()
      .catch(() => undefined)
      .finally(() => {
        setRefreshing(false);
        load();
      });
  }, [load]);

  const summary = coverageSummary(coverage);
  // KPI-1: sin cobertura, flag OFF, o diff sin items => nada renderizado.
  if (coverage === null || summary === null) return null;

  const ordered = severityOrder(coverage.items);

  return (
    <section className={styles.repoCoverageSection}>
      <div className={styles.repoCoverageHeader}>
        <h3 className={styles.repoCoverageTitle}>Cobertura del repo (scripts ticketeados)</h3>
        <button
          type="button"
          className={styles.repoCoverageRescan}
          onClick={rescan}
          disabled={refreshing}
        >
          {refreshing ? "Reescaneando..." : "Reescanear repo"}
        </button>
      </div>
      <p className={styles.repoCoverageSummary} title={workspace ? `Workspace: ${workspace}` : undefined}>
        {summary.covered} de {summary.total} items tienen script candidato ({summary.pct}%)
      </p>
      <ul className={styles.repoCoverageList}>
        {ordered.map((item, idx) => {
          const label = item.schema ? `${item.schema}.${item.name}` : String(item.name ?? "");
          return (
            <li key={`${label}-${idx}`} className={styles.repoCoverageRow}>
              <span className={styles.repoCoverageObject}>
                {label}
                {item.severity ? <span className={styles.repoCoverageSeverity}> · {item.severity}</span> : null}
              </span>
              {item.candidates.length === 0 ? (
                <span className={styles.repoCoverageUncovered}>sin candidatos</span>
              ) : (
                <span className={styles.repoCoverageCandidates}>
                  {item.candidates.map((cand, cidx) => (
                    <span key={`${cand.path}-${cidx}`} className={styles.repoCoverageCandidate}>
                      {cand.ticket ? <span className={styles.repoCoverageTicket}>#{cand.ticket}</span> : null}
                      <span className={styles.repoCoveragePath} title={cand.path}>
                        {cand.path}
                      </span>
                      {cand.matched_by === "SCHEMA.TABLE" ? (
                        <span className={styles.repoCoverageQualified} title="Match calificado por SCHEMA.TABLE">
                          calificado
                        </span>
                      ) : null}
                      <button
                        type="button"
                        className={styles.repoCoverageCopy}
                        onClick={() => void copyText(cand.path)}
                        title="Copiar ruta"
                      >
                        Copiar ruta
                      </button>
                    </span>
                  ))}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

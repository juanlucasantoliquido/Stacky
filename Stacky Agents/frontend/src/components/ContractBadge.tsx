/*
 * N1 — ContractBadge
 * Muestra el resultado del Contract Validator para una ejecución completada.
 * Score 0–100 con colores, lista de failures (errors) y warnings colapsable.
 */
import { useState } from "react";
import type { ContractResult } from "../types";
import styles from "./ContractBadge.module.css";

interface Props {
  result: ContractResult;
}

export default function ContractBadge({ result }: Props) {
  const [expanded, setExpanded] = useState(false);
  const totalIssues = result.failures.length + result.warnings.length;

  const tier =
    result.score >= 90
      ? "pass"
      : result.score >= 70
      ? "warn"
      : "fail";

  const tierLabel = tier === "pass" ? "OK" : tier === "warn" ? "REVISAR" : "FALLO";

  return (
    <div className={styles.badge} data-tier={tier}>
      <button
        className={styles.header}
        onClick={() => totalIssues > 0 && setExpanded((v) => !v)}
        aria-expanded={expanded}
        title={totalIssues > 0 ? "Ver detalles del contrato" : undefined}
      >
        <span className={styles.label}>CONTRATO</span>
        <span className={styles.score}>{result.score}/100</span>
        <span className={styles.status}>{tierLabel}</span>
        {totalIssues > 0 && (
          <span className={styles.count}>
            {result.failures.length > 0 && (
              <span data-sev="error">{result.failures.length} ✗</span>
            )}
            {result.warnings.length > 0 && (
              <span data-sev="warning">{result.warnings.length} ⚠</span>
            )}
            <span className={styles.chevron}>{expanded ? "▲" : "▼"}</span>
          </span>
        )}
      </button>

      {expanded && totalIssues > 0 && (
        <ul className={styles.list}>
          {result.failures.map((f, i) => (
            <li key={`e-${i}`} data-sev="error" className={styles.item}>
              <span className={styles.sev}>✗</span>
              <span>{f.message}</span>
            </li>
          ))}
          {result.warnings.map((w, i) => (
            <li key={`w-${i}`} data-sev="warning" className={styles.item}>
              <span className={styles.sev}>⚠</span>
              <span>{w.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

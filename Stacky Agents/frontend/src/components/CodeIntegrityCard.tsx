/**
 * CodeIntegrityCard.tsx — Plan 130: card "Integridad del código" en Diagnóstico.
 *
 * On-demand: el operador dispara el chequeo con un botón. La card decide su
 * propia visibilidad con un fetch de montaje (404/error de red → null, la
 * card no existe con la flag STACKY_CODE_INTEGRITY_ENABLED OFF).
 */
import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { CodeIntegrity } from "../api/endpoints";
import { reportToView, type CodeIntegrityReport } from "../diagnostics/codeIntegrityModel";
import styles from "./CodeIntegrityCard.module.css";

type Status = "checking-visibility" | "idle" | "running" | "done";

export default function CodeIntegrityCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [report, setReport] = useState<CodeIntegrityReport | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    CodeIntegrity.get()
      .then(() => {
        if (!cancelled) setStatus("idle");
      })
      .catch(() => {
        if (!cancelled) setHidden(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden) return null;
  if (status === "checking-visibility") return null;

  const runCheck = () => {
    setStatus("running");
    CodeIntegrity.get()
      .then((res: CodeIntegrityReport) => {
        setReport(res);
        setStatus("done");
      })
      .catch(() => {
        setReport({ ok: false, error: "network_error" });
        setStatus("done");
      });
  };

  const handleCopy = (copyText: string) => {
    navigator.clipboard
      .writeText(copyText)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        /* clipboard no disponible: no-op silencioso */
      });
  };

  const view = report ? reportToView(report) : null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <ShieldCheck size={16} />
          Integridad del código
        </h2>
        <button
          className={styles.runBtn}
          onClick={runCheck}
          disabled={status === "running"}
        >
          {status === "running" ? "Verificando…" : "Verificar ahora"}
        </button>
      </div>

      {view?.kind === "ok" && <p className={styles.okLine}>✓ {view.summary}</p>}

      {view?.kind === "findings" && (
        <>
          <p className={styles.summary}>{view.summary}</p>
          <pre className={styles.findings}>
            {view.findings
              .map(
                (f) =>
                  `${f.file}:${f.line} — ${f.import ? "import roto: " + f.import : f.message}`
              )
              .join("\n")}
          </pre>
          <button className={styles.copyBtn} onClick={() => handleCopy(view.copyText)}>
            {copied ? "Copiado ✓" : "📋 Copiar hallazgos"}
          </button>
        </>
      )}

      {view?.kind === "error" && <p className={styles.errorMsg}>{view.message}</p>}
    </div>
  );
}

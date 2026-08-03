import React, { useEffect, useState } from "react";
import { SetupGuide } from "../api/endpoints";
import { Dialog } from "./ui";
import {
  GITLAB_FALLBACK_GUIDE,
  canVerify,
  isServerGuide,
  stepsToHighlight,
  summarizeChecks,
  type GuideCheckResult,
  type SetupGuideDoc,
} from "../projects/setupGuideModel";
import styles from "./SetupGuideDialog.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Proveedor elegido en el formulario. En este plan solo GitLab tiene guía. */
  provider: string;
  values: {
    gitlab_url: string;
    gitlab_project: string;
    gitlab_token: string;
    gitlab_enable_engine: boolean;
    /** Plan 295 F5 — ruta del certificado de la empresa. Se LEE de values y se
     *  manda; este dialogo NO lo guarda en su estado, igual que el token. */
    gitlab_ca_bundle: string;
  };
  /** STACKY_SETUP_GUIDE_VERIFY_ENABLED: si está apagada, se oculta el bloque. */
  canRunVerify: boolean;
}

const WHERE_LABEL: Record<string, string> = {
  gitlab: "GitLab",
  stacky: "Stacky",
  windows: "Windows",
};

const ICON: Record<string, string> = { ok: "✅", fail: "❌", unknown: "❔" };

/**
 * Plan 259 F6.c — Panel de la guía de configuración, con verificación en vivo.
 *
 * Usa el `Dialog` canónico (plan 164): NO reimplementa portal, focus-trap ni
 * Escape. `adhocModalRatchet` está topado en FROZEN_MAX = 11 y no puede crecer,
 * así que cualquier `.tsx` nuevo con role="dialog"/aria-modal/createPortal que no
 * importe `Dialog` del barrel `ui` lo rompe.
 *
 * OJO: `size` se IGNORA si `bare === true`, así que NO se pasa `bare`.
 *
 * Se monta como HERMANO del modal que lo abre, nunca como hijo (hallazgo B12).
 */
export default function SetupGuideDialog({
  open,
  onClose,
  provider,
  values,
  canRunVerify,
}: Props) {
  const [guide, setGuide] = useState<SetupGuideDoc | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [checks, setChecks] = useState<GuideCheckResult[]>([]);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setChecks([]);
    setVerifyError(null);
    (async () => {
      try {
        // `raw*` no lanza en 4xx/5xx (deja data:null) pero SÍ re-lanza errores de
        // red y abort: hace falta try/catch ADEMÁS de mirar res.ok.
        const res = await SetupGuide.get(provider);
        const doc = res.ok ? res.data?.guide ?? null : null;
        if (cancelled) return;
        setGuide(doc ?? GITLAB_FALLBACK_GUIDE);
        setLoadError(!doc);
      } catch {
        if (cancelled) return;
        setGuide(GITLAB_FALLBACK_GUIDE);
        setLoadError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, provider]);

  async function runVerify() {
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await SetupGuide.verifyGitlab({
        gitlab_url: values.gitlab_url,
        gitlab_project: values.gitlab_project,
        // El token se pasa como ARGUMENTO y se descarta: no se guarda en el
        // estado de este diálogo.
        gitlab_token: values.gitlab_token,
        gitlab_enable_engine: values.gitlab_enable_engine,
        // Plan 295 F5 — sin esta linea el backend nunca recibe el certificado y
        // chk-tls evalua un TLS distinto del que usa el sync del proyecto.
        gitlab_ca_bundle: values.gitlab_ca_bundle,
      });
      if (res.ok && res.data?.checks) {
        setChecks(res.data.checks);
      } else {
        setChecks([]);
        setVerifyError(res.errorBody?.error ?? `No se pudo verificar (${res.status}).`);
      }
    } catch {
      setChecks([]);
      setVerifyError("No se pudo verificar: la conexión falló.");
    } finally {
      setVerifying(false);
    }
  }

  if (!guide) return null;

  const highlighted = new Set(stepsToHighlight(guide, checks));
  const summary = summarizeChecks(checks);
  const fromServer = isServerGuide(guide);
  const stepIndex = new Map(guide.steps.map((s, i) => [s.id, i + 1]));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title={`Cómo configurar ${guide.display_name}`}
    >
      <div className={styles.body}>
        {(loadError || !fromServer) && (
          <div className={styles.warnStrip}>
            Mostrando la guía básica embebida: no se pudo leer la guía del servidor.
          </div>
        )}

        <p className={styles.summary}>{guide.summary}</p>

        <ol className={styles.steps}>
          {guide.steps.map((step) => (
            <li
              key={step.id}
              className={highlighted.has(step.id) ? styles.stepHighlight : styles.step}
              aria-current={highlighted.has(step.id) ? "step" : undefined}
            >
              <div className={styles.stepHead}>
                <span className={styles.stepTitle}>{step.title}</span>
                <span className={styles.badge}>{WHERE_LABEL[step.where] ?? step.where}</span>
              </div>
              <p className={styles.stepDetail}>{step.detail}</p>
              {step.trap && <p className={styles.trap}>⚠️ {step.trap}</p>}
            </li>
          ))}
        </ol>

        {fromServer && canRunVerify && (
          <div className={styles.verifyBlock}>
            <div className={styles.verifyHead}>
              <button
                type="button"
                className={styles.btnVerify}
                onClick={runVerify}
                disabled={verifying || !canVerify(values)}
                aria-busy={verifying || undefined}
              >
                {verifying ? "Verificando…" : "Verificar ahora"}
              </button>
              {checks.length > 0 && (
                <span className={styles.verdict}>
                  {ICON[summary.verdict]} {summary.ok} bien · {summary.fail} mal ·{" "}
                  {summary.unknown} sin datos
                </span>
              )}
            </div>

            {!canVerify(values) && (
              <p className={styles.hint}>
                Cargá la URL base y el path del proyecto para poder verificar.
              </p>
            )}
            {verifyError && <p className={styles.verifyError}>{verifyError}</p>}

            {checks.length > 0 && (
              <ul className={styles.checks}>
                {checks.map((c) => {
                  const fixes = guide.checks.find((g) => g.id === c.id)?.fixes_step;
                  const n = fixes ? stepIndex.get(fixes) : undefined;
                  return (
                    <li key={c.id} className={styles.checkRow}>
                      <span className={styles.checkIcon}>{ICON[c.status]}</span>
                      <span className={styles.checkText}>
                        {c.message}
                        {c.detail ? ` (${c.detail})` : ""}
                        {c.status === "fail" && n ? ` → ver paso ${n}` : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}

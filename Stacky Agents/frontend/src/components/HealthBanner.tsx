import { useEffect, useState } from "react";
import { api } from "../api/client";
import { connectionMonitorOwnsBackendSurface } from "../services/connectionMonitor";
import styles from "./HealthBanner.module.css";

type CheckStatus = "ok" | "warning" | "error";

interface DiagCheck {
  id: string;
  label: string;
  status: CheckStatus;
  message: string;
  detail?: unknown;
}

interface DiagResponse {
  ok: boolean;
  checked_at: string;
  summary: { ok: number; warning: number; error: number };
  checks: DiagCheck[];
}

const POLL_MS = 30_000;
const DISMISS_TTL_MS = 30 * 60 * 1000;

interface DismissState {
  checkId: string;
  until: number;
}

function loadDismissed(): DismissState | null {
  try {
    const raw = localStorage.getItem("stacky.healthBanner.dismissed");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DismissState;
    if (Date.now() > parsed.until) {
      localStorage.removeItem("stacky.healthBanner.dismissed");
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function persistDismissed(checkId: string) {
  const state: DismissState = { checkId, until: Date.now() + DISMISS_TTL_MS };
  localStorage.setItem("stacky.healthBanner.dismissed", JSON.stringify(state));
}

const FIX_HINT: Record<string, { label: string; href?: string; tab?: string }> = {
  tracker: { label: "Abrir configuración", tab: "settings" },
  vscode_bridge: { label: "Abrir Diagnóstico", tab: "diagnostics" },
  vscode_vsix: { label: "Abrir Diagnóstico", tab: "diagnostics" },
  gh_auth: { label: "Abrir Diagnóstico", tab: "diagnostics" },
  database: { label: "Abrir Diagnóstico", tab: "diagnostics" },
  watchers: { label: "Activar proyecto", tab: "settings" },
};

export default function HealthBanner() {
  const [worst, setWorst] = useState<DiagCheck | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const data = await api.get<DiagResponse>("/api/diag/local");
        if (cancelled) return;
        const errored = data.checks.find((c) => c.status === "error") ?? null;
        const warned = errored ? null : data.checks.find((c) => c.status === "warning") ?? null;
        const next = errored ?? warned;
        const dismissed = loadDismissed();
        if (next && dismissed && dismissed.checkId === next.id) {
          setWorst(null);
        } else {
          setWorst(next);
        }
      } catch {
        if (!cancelled) {
          if (connectionMonitorOwnsBackendSurface()) {
            // Plan 192 F5: con el monitor de conexion activo, ConnectionBanner es
            // el dueno del aviso "backend caido"; HealthBanner no lo duplica.
            setWorst((prev) => (prev && prev.id === "backend" ? null : prev));
          } else {
            setWorst({
              id: "backend",
              label: "Backend",
              status: "error",
              message: "El backend no responde — revisá que esté corriendo.",
            });
          }
        }
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(poll, POLL_MS);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  if (!worst) return null;

  const hint = FIX_HINT[worst.id];
  const goTab = () => {
    if (!hint?.tab) return;
    const path = hint.tab === "settings" ? "/settings" : `/${hint.tab}`;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <div
      className={`${styles.banner} ${worst.status === "error" ? styles.error : styles.warning}`}
      role="alert"
    >
      <span className={styles.icon} aria-hidden="true">
        {worst.status === "error" ? "⚠" : "⚡"}
      </span>
      <div className={styles.body}>
        <strong className={styles.title}>{worst.label}</strong>
        <span className={styles.msg}>{worst.message}</span>
        {expanded && worst.detail ? (
          <pre className={styles.detail}>{JSON.stringify(worst.detail, null, 2)}</pre>
        ) : null}
      </div>
      <div className={styles.actions}>
        {hint?.tab ? (
          <button className={styles.fixBtn} onClick={goTab}>
            {hint.label}
          </button>
        ) : null}
        <button
          className={styles.detailBtn}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? "Menos" : "Detalles"}
        </button>
        <button
          className={styles.dismissBtn}
          onClick={() => {
            persistDismissed(worst.id);
            setWorst(null);
          }}
          aria-label="Ocultar por 30 minutos"
          title="Ocultar por 30 minutos"
        >
          ×
        </button>
      </div>
    </div>
  );
}

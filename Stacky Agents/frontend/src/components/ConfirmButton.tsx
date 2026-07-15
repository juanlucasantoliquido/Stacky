/**
 * Plan 136 F3 — Botón destructivo two-step (sin window.confirm).
 * Primer click ARMA (label de confirmación); segundo click dentro de timeoutMs
 * EJECUTA; expirado el timeout se desarma solo. Extraído del patrón validado de
 * FinishWorkButton.tsx:287-310, sumándole el desarme automático.
 * La máquina de estados vive en services/uiGuards.ts (nextConfirmState, testeada).
 */
import { useEffect, useRef, useState } from "react";
import { nextConfirmState, type ConfirmState } from "../services/uiGuards";
import styles from "./ConfirmButton.module.css";

interface ConfirmButtonProps {
  label: React.ReactNode;
  confirmLabel?: React.ReactNode; // default "⚠ Confirmar"
  onConfirm: () => void;
  disabled?: boolean;
  busy?: boolean;      // deshabilita y desarma mientras la acción corre
  className?: string;  // clase del estado idle (hereda el estilo local del caller)
  title?: string;
  timeoutMs?: number;  // default 4000
}

export default function ConfirmButton({
  label,
  confirmLabel = "⚠ Confirmar",
  onConfirm,
  disabled,
  busy,
  className,
  title,
  timeoutMs = 4000,
}: ConfirmButtonProps) {
  const [state, setState] = useState<ConfirmState>("idle");
  const timerRef = useRef<number | null>(null);

  function clearTimer() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  useEffect(() => () => clearTimer(), []);

  // disabled/busy externos desarman (evento "disable" de la máquina).
  useEffect(() => {
    if ((disabled || busy) && state === "armed") {
      clearTimer();
      setState(nextConfirmState(state, "disable").state);
    }
  }, [disabled, busy, state]);

  function handleClick() {
    const next = nextConfirmState(state, "click");
    clearTimer();
    setState(next.state);
    if (next.fire) {
      onConfirm();
      return;
    }
    timerRef.current = window.setTimeout(() => {
      setState((s) => nextConfirmState(s, "timeout").state);
      timerRef.current = null;
    }, timeoutMs);
  }

  return (
    <button
      type="button"
      className={state === "armed" ? styles.armed : className}
      onClick={handleClick}
      disabled={disabled || busy}
      title={state === "armed" ? "Click de nuevo para confirmar (se desarma solo en unos segundos)" : title}
      aria-pressed={state === "armed"}
    >
      {state === "armed" ? confirmLabel : label}
    </button>
  );
}

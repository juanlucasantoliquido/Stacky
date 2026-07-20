/*
 * Plan 151 F3 — Tour de bienvenida v2 (reescritura del prototipo).
 *
 * Componente feature accesible: consume la lógica pura de F0/F1, las primitivas
 * del plan 138 (Card/Button vía barrel), los tokens de motion del 143 y el
 * --focus-ring del 141. La decisión de mostrarse (auto vs on-demand) la maneja
 * el store (onboardingStore) + el effect de F5; acá solo se renderiza.
 *
 * C3: la primitiva Card NO es forwardRef y no acepta ref/tabIndex/data-* ⇒ el
 *     wrapper focusable es un <div> propio del feature; Card va adentro.
 * C7: el listener de teclado ignora inputs/contenteditable y NO hace
 *     preventDefault ⇒ no colisiona con la paleta Ctrl+K (129).
 * R5: el spotlight se posiciona con custom props seteadas de forma imperativa
 *     (ref + setProperty) para NO usar inline-style y no tocar el ratchet 138.
 */
import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Card, Button } from "./ui";
import { STEPS } from "../services/onboardingSteps";
import { nextStep, prevStep, isLastStep } from "../services/onboarding";
import { useOnboardingStore } from "../store/onboardingStore";
import styles from "./OnboardingTour.module.css";

/** querySelector protegido: ancla ausente ⇒ null (card centrada, sin crash). */
function safeRect(sel: string): DOMRect | null {
  try {
    const el = document.querySelector(sel);
    return el ? el.getBoundingClientRect() : null;
  } catch {
    return null;
  }
}

export default function OnboardingTour() {
  const open = useOnboardingStore((s) => s.open);
  const close = useOnboardingStore((s) => s.closeTour);
  const [i, setI] = useState(0);
  const [anchored, setAnchored] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const spotlightRef = useRef<HTMLDivElement>(null);

  // Al abrir: reset al paso 0 + foco al wrapper + listener Esc/flechas.
  useEffect(() => {
    if (!open) return;
    setI(0);
    cardRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      // C7: no interferir con campos editables ni con la paleta.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setI((v) => nextStep(v, STEPS.length));
      else if (e.key === "ArrowLeft") setI((v) => prevStep(v));
      // C7: sin preventDefault/stopPropagation — otros listeners siguen vivos.
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // Posicionar el spotlight imperativamente (custom props) — R5.
  useLayoutEffect(() => {
    if (!open) {
      setAnchored(false);
      return;
    }
    const target = STEPS[i]?.target ?? null;
    const rect = target ? safeRect(target) : null;
    const el = spotlightRef.current;
    if (rect && el) {
      el.style.setProperty("--r-top", `${rect.top}px`);
      el.style.setProperty("--r-left", `${rect.left}px`);
      el.style.setProperty("--r-w", `${rect.width}px`);
      el.style.setProperty("--r-h", `${rect.height}px`);
      setAnchored(true);
    } else {
      setAnchored(false);
    }
  }, [open, i]);

  if (!open) return null;
  const step = STEPS[i];
  const last = isLastStep(i, STEPS.length);
  const posClass = anchored ? styles[step.position] : styles.centered;

  return createPortal(
    <div
      className={styles.root}
      role="dialog"
      aria-modal="true"
      aria-label="Tour de bienvenida de Stacky Agents"
    >
      <div
        className={anchored ? styles.backdrop : `${styles.backdrop} ${styles.backdropDim}`}
        onClick={close}
        aria-hidden="true"
      />
      <div
        ref={spotlightRef}
        className={anchored ? styles.spotlight : `${styles.spotlight} ${styles.spotlightHidden}`}
        aria-hidden="true"
      />
      <div
        ref={cardRef}
        tabIndex={-1}
        className={`${styles.cardWrap} ${posClass}`}
        data-anchored={anchored ? "1" : "0"}
      >
        <Card padding="md" elevated>
          <h3 className={styles.title}>{step.title}</h3>
          <p className={styles.body}>{step.body}</p>
          <div className={styles.footer}>
            <span className={styles.count}>
              {i + 1} / {STEPS.length}
            </span>
            <div className={styles.actions}>
              <Button variant="ghost" onClick={close}>
                Saltar
              </Button>
              {i > 0 && (
                <Button variant="secondary" onClick={() => setI(prevStep(i))}>
                  Anterior
                </Button>
              )}
              <Button
                variant="primary"
                onClick={() => (last ? close() : setI(nextStep(i, STEPS.length)))}
              >
                {last ? "Empezar" : "Siguiente"}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>,
    document.body,
  );
}

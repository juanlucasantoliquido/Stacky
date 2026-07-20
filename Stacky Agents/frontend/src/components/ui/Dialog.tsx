import { ReactNode, RefObject, useEffect, useId, useRef, KeyboardEvent, MouseEvent } from "react";
import { createPortal } from "react-dom";
import styles from "./Dialog.module.css";
import {
  dialogKeydownAction,
  canCloseByGuard,
  FOCUSABLE_SELECTOR,
} from "./dialogKeyboard";

/**
 * Plan 164 F1 — Primitiva canónica de diálogo modal. ÚNICO lugar del sistema de
 * diseño con efectos de DOM (portal, focus-trap, restore-focus, scroll-lock).
 * Toda la lógica de decisión vive en dialogKeyboard.ts (puro y testeado).
 * Sin style inline (uiDebtRatchet forcedZero para components/ui/): estilos por
 * clase de Dialog.module.css con tokens de theme.css.
 */
export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  /** Guarda de cierre: si dirty/busy, Escape y backdrop NO cierran (plan 136). */
  closeGuard?: { dirty: boolean; busy: boolean };
  /** aria-label si no hay title textual. */
  ariaLabel?: string;
  /** Ancho/variante visual. */
  size?: "sm" | "md" | "lg";
  /** Foco inicial: por defecto el primer enfocable (o el que ya tenga autoFocus). */
  initialFocusRef?: RefObject<HTMLElement>;
  /** Muestra el botón ✕ del header (dismiss). Default true si hay title. */
  showClose?: boolean;
  /** Clase extra opcional para el footer/acciones (composición de derivados). */
  footer?: ReactNode;
  /**
   * Modo migración (F1 stress-test): la primitiva aporta SÓLO comportamiento
   * (portal + role=dialog + Escape + focus-trap + restore-focus + scroll-lock).
   * El panel NO impone chrome (bg/border/padding/header/footer): el modal
   * migrado conserva su propia clase visual vía panelClassName y su contenido
   * (header/footer/✕ propios) tal cual, como children. Los derivados de marca
   * (Confirm/Alert/Prompt) usan el modo estructurado (bare=false).
   */
  bare?: boolean;
  /** Modo bare: clase visual del panel (la `.modal` original del modal migrado). */
  panelClassName?: string;
}

// C6b — contador de diálogos abiertos a nivel módulo: scroll-lock del body +
// fondo (#root) inerte mientras haya AL MENOS un diálogo montado. Robusto a
// StrictMode (cada mount balancea su unmount).
let openDialogCount = 0;

function acquireBackdrop(): void {
  openDialogCount += 1;
  if (openDialogCount === 1) {
    document.body.classList.add("dialogScrollLock");
    const root = document.getElementById("root");
    if (root) root.setAttribute("inert", "");
  }
}

function releaseBackdrop(): void {
  openDialogCount = Math.max(0, openDialogCount - 1);
  if (openDialogCount === 0) {
    document.body.classList.remove("dialogScrollLock");
    const root = document.getElementById("root");
    if (root) root.removeAttribute("inert");
  }
}

export default function Dialog({
  open,
  onClose,
  title,
  children,
  closeGuard,
  ariaLabel,
  size = "md",
  initialFocusRef,
  showClose = true,
  footer,
  bare = false,
  panelClassName,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    // Guardar el disparador para restaurar el foco al cerrar (restore-focus).
    const trigger = document.activeElement as HTMLElement | null;
    acquireBackdrop();
    if (panel) {
      const initial = initialFocusRef?.current;
      if (initial) {
        initial.focus();
      } else if (panel.contains(document.activeElement) && document.activeElement !== panel) {
        // autoFocus ya colocó el foco dentro del panel (p.ej. input del PromptDialog
        // o botón primario del ConfirmDialog): respetarlo, no robarlo.
      } else {
        const focusables = panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        if (focusables.length > 0) focusables[0].focus();
        else panel.focus();
      }
    }
    return () => {
      // C6b/C6d: liberar el fondo inerte ANTES de restaurar el foco (si el
      // trigger sigue en el DOM; si ya se desprendió, no forzar foco a un nodo
      // detached — quedaría un no-op silencioso).
      releaseBackdrop();
      if (trigger && document.contains(trigger)) trigger.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const panel = panelRef.current;
    if (!panel) return;
    const focusables = Array.from(
      panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    );
    const active = document.activeElement as HTMLElement | null;
    const idx = active ? focusables.indexOf(active) : -1;
    const atFirst = focusables.length === 0 || idx <= 0;
    const atLast = focusables.length === 0 || idx === focusables.length - 1;
    const action = dialogKeydownAction(e.key, e.shiftKey, { atFirst, atLast });
    if (action === null) return;
    if (action === "close") {
      if (canCloseByGuard(closeGuard)) {
        e.preventDefault();
        e.stopPropagation(); // C6a: los portales burbujean por el árbol de React
        onClose();
      }
      return;
    }
    // focus-trap: wrap explícito en ambos extremos.
    e.preventDefault();
    e.stopPropagation(); // C6a
    if (focusables.length === 0) return;
    if (action === "focus-first") focusables[0].focus();
    else focusables[focusables.length - 1].focus();
  };

  const handleOverlayClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && canCloseByGuard(closeGuard)) onClose();
  };

  const labelledBy = title && !bare ? titleId : undefined;

  const panelInner = bare ? (
    // Modo migración: el modal conserva su chrome/contenido tal cual (children).
    children
  ) : (
    <>
      {(title || showClose) && (
        <div className={styles.header}>
          {title ? (
            <div className={styles.title} id={titleId}>
              {title}
            </div>
          ) : (
            <div className={styles.title} />
          )}
          {showClose && (
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              aria-label="Cerrar"
            >
              ✕
            </button>
          )}
        </div>
      )}
      <div className={styles.body}>{children}</div>
      {footer && <div className={styles.footer}>{footer}</div>}
    </>
  );

  const panelClass = bare
    ? panelClassName ?? ""
    : `${styles.panel} ${styles[size]}`;

  const panel = (
    <div className={styles.overlay} onClick={handleOverlayClick} onKeyDown={handleKeyDown}>
      <div
        ref={panelRef}
        className={panelClass}
        role="dialog"
        aria-modal="true"
        aria-label={title && !bare ? undefined : ariaLabel}
        aria-labelledby={labelledBy}
        tabIndex={-1}
      >
        {panelInner}
      </div>
    </div>
  );

  return createPortal(panel, document.body);
}

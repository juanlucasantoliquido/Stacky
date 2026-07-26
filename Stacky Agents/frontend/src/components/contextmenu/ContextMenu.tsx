import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  armTransition,
  clampMenuPosition,
  menuKeydown,
  type ArmState,
} from "../../services/contextMenuModel";
import type { EntityAction, EntityActionContext } from "../../services/entityActions";
import styles from "./ContextMenu.module.css";

/**
 * Plan 175 F3 — UN menú contextual para todas las entidades.
 *
 * Las acciones con efecto se ARMAN antes de disparar: el primer click avisa (y
 * se ve distinto), el segundo ejecuta. Es la confirmación humana sin depender de
 * un diálogo, y hace falta porque un menú que aparece con el clic derecho está a
 * un click de distancia de borrar algo.
 */
export function ContextMenu({
  open,
  x,
  y,
  actions,
  ctx,
  openedByKeyboard,
  onClose,
}: {
  open: boolean;
  x: number;
  y: number;
  actions: EntityAction[];
  ctx: EntityActionContext;
  openedByKeyboard: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [indice, setIndice] = useState(0);
  const [arm, setArm] = useState<ArmState>({ armedId: null });

  useEffect(() => {
    if (!open) {
      setArm({ armedId: null });
      setIndice(0);
    }
  }, [open]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !open) return;
    const caja = el.getBoundingClientRect();
    const p = clampMenuPosition(x, y, caja.width, caja.height, window.innerWidth, window.innerHeight);
    el.style.left = `${p.left}px`;
    el.style.top = `${p.top}px`;
    if (openedByKeyboard) el.focus({ preventScroll: true });
  }, [open, x, y, openedByKeyboard]);

  useEffect(() => {
    if (!open) return;
    const alClickear = (ev: MouseEvent) => {
      if (!ref.current?.contains(ev.target as Node)) onClose();
    };
    document.addEventListener("mousedown", alClickear);
    return () => document.removeEventListener("mousedown", alClickear);
  }, [open, onClose]);

  if (!open) return null;

  function ejecutar(a: EntityAction) {
    const r = armTransition(arm, { type: "activate", id: a.id, effect: a.effect });
    setArm(r.state);
    if (!r.fire) return;
    void a.run(ctx);
    onClose();
  }

  return createPortal(
    <div
      ref={ref}
      className={styles.menu}
      role="menu"
      aria-label="Acciones"
      tabIndex={-1}
      onKeyDown={(ev) => {
        const r = menuKeydown(ev.key, indice, actions.length);
        if (r.kind === "none") return;
        ev.preventDefault();
        if (r.kind === "close") onClose();
        else if (r.kind === "move") setIndice(r.index);
        else if (actions[indice]) ejecutar(actions[indice]);
      }}
    >
      {actions.map((a, i) => (
        <button
          key={a.id}
          type="button"
          role="menuitem"
          tabIndex={-1}
          className={`${styles.item} ${i === indice ? styles.active : ""} ${
            arm.armedId === a.id ? styles.armed : ""
          }`}
          onMouseEnter={() => setIndice(i)}
          onClick={() => ejecutar(a)}
        >
          <span className={styles.icon} aria-hidden="true">
            {a.icon}
          </span>
          {arm.armedId === a.id ? `${a.label} — confirmá` : a.label}
        </button>
      ))}
      {actions.length === 0 && <div className={styles.item}>Sin acciones disponibles</div>}
    </div>,
    document.body,
  );
}

export default ContextMenu;

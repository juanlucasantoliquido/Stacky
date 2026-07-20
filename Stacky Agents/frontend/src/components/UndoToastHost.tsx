/**
 * UndoToastHost.tsx — Plan 185 F2/F4. Host global (montado una vez en App.tsx)
 * que muestra los pendientes del undoManager como toasts de la casa con botón
 * "Deshacer", barra de countdown y atajo Ctrl+Z.
 *
 * Cero inline-style (ratchet uiDebt: presupuesto 0 para .tsx nuevos): todo el
 * estilo vive en UndoToastHost.module.css; el valor dinámico del countdown se
 * setea por ref + setProperty en useEffect.
 *
 * La accesibilidad la aporta el propio <Toast> (usa role de alerta y su
 * anuncio asertivo), por eso el host NO declara ninguna región viva propia
 * (197 §6.11 / 185 C2).
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Toast from "./Toast";
import styles from "./UndoToastHost.module.css";
import {
  pending,
  subscribe,
  undo,
  undoLatest,
  flushAll,
  setBypass,
  type PendingUndoable,
} from "../services/undoManager";
import { visibleToasts, shouldHandleUndoKey } from "../services/undoToastModel";
import { getBoolFlag } from "../services/flagGate";

const FLAG = "STACKY_UNDO_UNIVERSAL_ENABLED";

export default function UndoToastHost() {
  const [items, setItems] = useState<PendingUndoable[]>([]);
  // dismiss OCULTA el toast localmente; la gracia sigue corriendo hasta su
  // commit normal (cerrar ≠ deshacer; cero API nueva, cero pérdida).
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  // Suscripción al manager: refresca pendientes y poda `dismissed` de ids que
  // ya no están pendientes (evita que un id reutilizado herede un dismiss viejo).
  useEffect(() => {
    const refresh = () => {
      const cur = pending();
      setItems(cur);
      setDismissed((prev) => {
        if (prev.size === 0) return prev;
        const ids = new Set(cur.map((p) => p.id));
        let changed = false;
        const next = new Set<string>();
        for (const id of prev) {
          if (ids.has(id)) next.add(id);
          else changed = true;
        }
        return changed ? next : prev;
      });
    };
    refresh();
    return subscribe(refresh);
  }, []);

  // Flag leída UNA vez al montar vía flagGate (único lector de flags, 197 §6.1;
  // KPI-2). Staleness aceptada (C6): un toggle aplica al próximo reload del
  // dashboard (mismo contrato que las flags restart_required del arnés).
  useEffect(() => {
    let alive = true;
    getBoolFlag(FLAG).then((on) => {
      if (alive && !on) setBypass(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // [ADICIÓN ARQUITECTO] Ctrl+Z global. El plan 172 (registry de atajos) NO está
  // implementado en esta rama, así que se usa el fallback DIRECTO que el propio
  // doc 185 prescribe para el caso "sin 172": listener window + guard PURO
  // shouldHandleUndoKey. Cuando el 172 exista, este listener migra a su
  // shortcutRegistry (197 §6.4 — escenario invertido §6.7).
  useEffect(() => {
    const handler = (ev: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      const ok = shouldHandleUndoKey(
        {
          key: ev.key,
          ctrlKey: ev.ctrlKey,
          metaKey: ev.metaKey,
          altKey: ev.altKey,
          shiftKey: ev.shiftKey,
        },
        active
          ? { tagName: active.tagName, isContentEditable: active.isContentEditable }
          : null,
      );
      if (ok) {
        ev.preventDefault();
        undoLatest();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // F4 — garantía de no-pérdida: flush en pagehide/visibilitychange y unmount.
  useEffect(() => {
    const flush = () => flushAll("pagehide");
    window.addEventListener("pagehide", flush);
    const onVis = () => {
      if (document.visibilityState === "hidden") flushAll("pagehide");
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", onVis);
      // Nota StrictMode (C9): en dev el unmount fantasma dispara flushAll con
      // CERO pendientes (aún no hubo acciones) ⇒ inocuo; sin guards extra.
      // Nota de límite: commits async lanzados en pagehide pueden no completarse
      // si el browser mata el proceso; mitigación real = gracia corta (≤15 s).
      // keepalive/sendBeacon fuera de scope (185 §6).
      flushAll("manual");
    };
  }, []);

  const visible = visibleToasts(items).filter((p) => !dismissed.has(p.id));
  if (visible.length === 0) return null;

  return (
    <div className={styles.host}>
      {visible.map((p) => (
        <UndoItem
          key={p.id}
          p={p}
          onUndo={() => undo(p.id)}
          onDismiss={() => setDismissed((prev) => new Set(prev).add(p.id))}
        />
      ))}
    </div>
  );
}

function UndoItem({
  p,
  onUndo,
  onDismiss,
}: {
  p: PendingUndoable;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  const barRef = useRef<HTMLDivElement | null>(null);
  // Duración del countdown por ref (setProperty) ANTES del paint: mantiene el
  // module.css sin literales de tiempo (ratchet) y evita el flash de una
  // animation-duration inválida en el primer frame.
  useLayoutEffect(() => {
    const el = barRef.current;
    if (el) {
      el.style.setProperty(
        "--undo-grace-ms",
        String(p.expiresAt - p.createdAt) + "ms",
      );
    }
  }, [p.expiresAt, p.createdAt]);

  return (
    <div className={styles.item}>
      <Toast
        toast={{
          variant: "success",
          body: p.label,
          action: { label: "Deshacer", onAction: onUndo },
        }}
        onClose={onDismiss}
        inStack
      />
      <div className={styles.countdownBar} ref={barRef} />
    </div>
  );
}

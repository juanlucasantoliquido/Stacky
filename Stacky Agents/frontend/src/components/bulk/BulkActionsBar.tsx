/**
 * Plan 187 F3 — barra flotante contextual de acciones en lote.
 *
 * Aparece SOLO con selección (o lote en curso) y desaparece al no haberla.
 * Acciones destructivas usan armado de dos pasos (nextArmed, bulkModel) —
 * cero diálogos nativos (ratchet 185/gate 164). Primitivas Button/Spinner del
 * barrel ui (cero tags crudos, formDebtRatchet). Cero style inline (K8).
 */
import { useEffect, useState } from "react";
import { Button, Spinner } from "../ui";
import { ARM_AUTO_DISARM_MS, nextArmed } from "../../services/bulkModel";
import styles from "./BulkActionsBar.module.css";

export interface BulkAction {
  /** estable kebab-case, ej. "discard-selected". */
  id: string;
  label: (n: number) => string;
  /** Solo para destructive: label del estado armado. */
  armedLabel?: (n: number) => string;
  /** true ⇒ requiere armado de dos pasos (HITL). */
  destructive: boolean;
  /** la página cierra sobre su selección/worker. */
  run: () => void;
}

export interface BulkActionsBarProps {
  count: number;
  actions: BulkAction[];
  running: boolean;
  progress: { done: number; total: number } | null;
  onClear: () => void;
}

export default function BulkActionsBar({
  count,
  actions,
  running,
  progress,
  onClear,
}: BulkActionsBarProps) {
  const [armed, setArmed] = useState<string | null>(null);

  // Cambió la selección ⇒ desarmar.
  useEffect(() => {
    setArmed(null);
  }, [count]);

  // Auto-desarme tras ARM_AUTO_DISARM_MS.
  useEffect(() => {
    if (armed === null) return;
    const t = setTimeout(() => setArmed(null), ARM_AUTO_DISARM_MS);
    return () => clearTimeout(t);
  }, [armed]);

  if (count === 0 && !running) return null;

  function onActionClick(action: BulkAction) {
    if (!action.destructive) {
      action.run();
      return;
    }
    const r = nextArmed(armed, action.id);
    setArmed(r.armed);
    if (r.execute) action.run();
  }

  return (
    <div className={styles.bar} role="toolbar" aria-label="Acciones en lote">
      {running && progress ? (
        <span className={styles.progress} aria-live="polite">
          <Spinner size={14} />
          Ejecutando… {progress.done}/{progress.total}
        </span>
      ) : (
        <span className={styles.count} aria-live="polite">
          {count} seleccionadas
        </span>
      )}
      <span className={styles.spacer} />
      <span className={styles.actions}>
        {actions.map((action) => {
          const isArmed = action.destructive && armed === action.id;
          const label = isArmed
            ? action.armedLabel?.(count) ?? action.label(count)
            : action.label(count);
          return (
            <Button
              key={action.id}
              size="sm"
              variant={action.destructive ? "danger" : "secondary"}
              disabled={running}
              onClick={() => onActionClick(action)}
            >
              {label}
            </Button>
          );
        })}
        <Button size="sm" variant="ghost" disabled={running} onClick={onClear}>
          Deseleccionar
        </Button>
      </span>
    </div>
  );
}

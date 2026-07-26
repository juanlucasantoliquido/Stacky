import { useEffect, useRef, useState } from "react";

import {
  EMPTY_TABLE_PREFS,
  isColVisible,
  toggleColumn,
  type ColumnDef,
  type TablePrefs,
} from "../services/tablePrefs";
import { Button, Checkbox } from "./ui";
import styles from "./TableColumnsMenu.module.css";

/**
 * Plan 173 F4 — Qué columnas ve cada operador.
 *
 * La última visible no se puede desmarcar: lo garantiza `toggleColumn`, que ya
 * tiene su test. Una tabla sin columnas no es una tabla.
 */
export function TableColumnsMenu({
  columns,
  prefs,
  onChange,
}: {
  columns: ColumnDef[];
  prefs: TablePrefs;
  onChange: (next: TablePrefs) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const alClickear = (ev: MouseEvent) => {
      if (!wrapRef.current?.contains(ev.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", alClickear);
    return () => document.removeEventListener("mousedown", alClickear);
  }, [abierto]);

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <Button size="sm" onClick={() => setAbierto((v) => !v)} aria-expanded={abierto}>
        Columnas
      </Button>
      {abierto && (
        <div className={styles.popover} role="group" aria-label="Columnas visibles">
          {columns.map((c) => (
            <Checkbox
              key={c.id}
              label={c.label}
              aria-label={c.label}
              checked={isColVisible(prefs, c.id)}
              onChange={() => onChange(toggleColumn(prefs, c.id, columns))}
            />
          ))}
          <div className={styles.footer}>
            <Button
              size="sm"
              // Restablecer las columnas no tiene por qué perder el orden que el
              // operador eligió: son dos preferencias distintas.
              onClick={() => onChange({ ...EMPTY_TABLE_PREFS, sort: prefs.sort })}
            >
              Restablecer columnas
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default TableColumnsMenu;

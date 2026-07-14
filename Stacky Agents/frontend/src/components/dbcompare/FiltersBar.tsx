import { useEffect, useState } from "react";
import type { ObjectType, Severity } from "./dbcompareTypes";
import type { DiffFilters } from "./filterLogic";
import styles from "./dbcompare.module.css";

const SEVERITIES: Severity[] = ["danger", "warn", "info"];
const OBJECT_TYPES: ObjectType[] = ["table", "view", "sequence"];
const OBJECT_TYPE_LABEL: Record<ObjectType, string> = { table: "Tablas", view: "Vistas", sequence: "Secuencias" };

interface Props {
  filters: DiffFilters;
  onChange: (f: DiffFilters) => void;
  filteredCount: number;
  totalCount: number;
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Plan 124 F5 — barra de filtros: chips de severidad, select de tipo, texto con debounce
 * 250ms. Toda la evaluación real vive en filterLogic.ts (ya testeado, KPI-2). */
export function FiltersBar({ filters, onChange, filteredCount, totalCount }: Props) {
  const [textDraft, setTextDraft] = useState(filters.text);

  useEffect(() => {
    const t = setTimeout(() => {
      if (textDraft !== filters.text) onChange({ ...filters, text: textDraft });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textDraft]);

  return (
    <div className={styles.filtersBar}>
      {SEVERITIES.map((s) => (
        <button
          key={s}
          type="button"
          className={styles.chip}
          aria-pressed={filters.severities.includes(s)}
          onClick={() => onChange({ ...filters, severities: toggle(filters.severities, s) })}
        >
          {s}
        </button>
      ))}
      <select
        value={filters.objectTypes[0] ?? ""}
        onChange={(e) =>
          onChange({ ...filters, objectTypes: e.target.value ? [e.target.value as ObjectType] : [] })
        }
      >
        <option value="">Todos los tipos</option>
        {OBJECT_TYPES.map((t) => (
          <option key={t} value={t}>
            {OBJECT_TYPE_LABEL[t]}
          </option>
        ))}
      </select>
      <input
        type="text"
        placeholder="Buscar por nombre o tipo de cambio…"
        value={textDraft}
        onChange={(e) => setTextDraft(e.target.value)}
      />
      <span className={styles.recency}>
        {filteredCount} de {totalCount} objetos
      </span>
    </div>
  );
}

export default FiltersBar;

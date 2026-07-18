// Plan 181 F5 — barra de control del masking del data-diff. Los valores YA
// llegan enmascarados del backend (F3); esta barra solo lista las columnas
// protegidas y ofrece el HITL de revelar/ocultar por columna (1 click,
// persistido). Se auto-oculta si no hay nada enmascarado (y con la flag OFF el
// backend no manda `masked_columns`, así que tampoco aparece).
//
// Sin tests RTL/jsdom (gap estructural del repo): la lógica pura vive en
// maskingLogic.ts (vitest); este archivo es JSX, verificado con tsc --noEmit.
// CERO estilos inline (uiDebtRatchet): todas las clases en dbcompare.module.css.
import { DbCompareMasking } from "../../api/endpoints";
import { collectMaskedTables } from "./maskingLogic";
import styles from "./dbcompare.module.css";

interface Props {
  tables: Record<string, unknown>;
  onChanged: () => void;
}

export function DataMaskingBar({ tables, onChanged }: Props) {
  const masked = collectMaskedTables(tables);
  if (masked.length === 0) return null;

  const setState = (
    schema: string,
    table: string,
    column: string,
    state: "visible" | "auto",
  ) => {
    DbCompareMasking.putOverride({ schema, table, column, state })
      .then(onChanged)
      .catch(() => undefined);
  };

  return (
    <section className={styles.maskingBar}>
      <p className={styles.maskingTitle}>Columnas protegidas</p>
      <p className={styles.maskingLegend}>Los scripts del bundle contienen valores reales.</p>
      {masked.map((t) => (
        <div key={t.key} className={styles.maskingTableRow}>
          <span className={styles.maskingTableName}>
            {t.schema}.{t.table}
          </span>
          {t.maskedColumns.map((col) => (
            <span key={col} className={styles.maskingChip}>
              {col}
              <button
                type="button"
                className={styles.maskingReveal}
                onClick={() => setState(t.schema, t.table, col, "visible")}
              >
                Revelar
              </button>
              <button
                type="button"
                className={styles.maskingHide}
                onClick={() => setState(t.schema, t.table, col, "auto")}
              >
                Ocultar de nuevo
              </button>
            </span>
          ))}
        </div>
      ))}
    </section>
  );
}

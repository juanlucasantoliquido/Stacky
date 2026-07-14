import { useEffect } from "react";
import type { DbSnapshot, DiffItem, ForeignKeyInfo, IndexInfo, UniqueConstraintInfo, CheckConstraintInfo } from "./dbcompareTypes";
import { buildColumnRows, buildSectionRows, type SectionRow } from "./sideBySide";
import styles from "./dbcompare.module.css";

interface Props {
  item: DiffItem;
  sourceSnapshot: DbSnapshot | null;
  targetSnapshot: DbSnapshot | null;
  onClose: () => void;
}

function fkKey(fk: ForeignKeyInfo): string {
  return `${fk.columns.join(",")}=>${fk.referred_schema}.${fk.referred_table}(${fk.referred_columns.join(",")})`;
}
function indexKey(ix: IndexInfo): string {
  return `${ix.unique}:${ix.columns.join(",")}`;
}
function uniqueKey(u: UniqueConstraintInfo): string {
  return u.columns.join(",");
}
function checkKey(c: CheckConstraintInfo): string {
  return c.sqltext.trim().toUpperCase();
}

function SectionTable<T>({ title, rows, render }: { title: string; rows: SectionRow<T>[]; render: (v: T) => string }) {
  if (rows.length === 0) return null;
  return (
    <details open>
      <summary>{title}</summary>
      <table className={styles.sideBySideTable}>
        <thead>
          <tr>
            <th>Origen</th>
            <th>Destino</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.state === "added" ? styles.rowAdded : r.state === "removed" ? styles.rowRemoved : undefined}>
              <td>{r.source ? render(r.source) : "—"}</td>
              <td>{r.target ? render(r.target) : "—"}</td>
              <td>{r.state}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

/**
 * Plan 124 F5 — panel lateral de drill-down side-by-side. Toda la lógica de union/comparación
 * viene de sideBySide.ts (ya testeado). `sourceSnapshot`/`targetSnapshot` los cachea
 * DbComparePage (1 fetch por run, al abrir el primer drill-down).
 */
export function ObjectDrilldown({ item, sourceSnapshot, targetSnapshot, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sourceTable = sourceSnapshot?.schemas[item.schema]?.tables[item.name] ?? null;
  const targetTable = targetSnapshot?.schemas[item.schema]?.tables[item.name] ?? null;
  const sourceView = sourceSnapshot?.schemas[item.schema]?.views[item.name] ?? null;
  const targetView = targetSnapshot?.schemas[item.schema]?.views[item.name] ?? null;

  const columnRows = item.object_type === "table" ? buildColumnRows(item, sourceTable, targetTable) : [];
  const fkRows = buildSectionRows(sourceTable?.foreign_keys ?? [], targetTable?.foreign_keys ?? [], fkKey);
  const indexRows = buildSectionRows(sourceTable?.indexes ?? [], targetTable?.indexes ?? [], indexKey);
  const uniqueRows = buildSectionRows(sourceTable?.unique_constraints ?? [], targetTable?.unique_constraints ?? [], uniqueKey);
  const checkRows = buildSectionRows(sourceTable?.check_constraints ?? [], targetTable?.check_constraints ?? [], checkKey);

  const pkSource = (sourceTable?.primary_key.columns ?? []).join(", ");
  const pkTarget = (targetTable?.primary_key.columns ?? []).join(", ");

  return (
    <div className={styles.drilldownOverlay} onClick={onClose}>
      <div className={styles.drilldownPanel} onClick={(e) => e.stopPropagation()}>
        <div className={styles.cardHeader}>
          <strong>
            {item.schema}.{item.name}
          </strong>
          <span>
            <span className={styles.chip}>{item.severity}</span> <span className={styles.chip}>{item.action}</span>
          </span>
        </div>
        <button onClick={onClose}>Cerrar</button>

        {item.object_type === "table" && (
          <>
            <details open>
              <summary>Columnas</summary>
              <table className={styles.sideBySideTable}>
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Origen</th>
                    <th>Destino</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {columnRows.map((r) => (
                    <tr key={r.name} className={r.state === "added" ? styles.rowAdded : r.state === "removed" ? styles.rowRemoved : undefined}>
                      <td>{r.name}</td>
                      <td className={r.changedFields.includes("type") || r.changedFields.length ? styles.cellChanged : undefined}>
                        {r.source ? `${r.source.type}${r.source.nullable ? " NULL" : " NOT NULL"}` : "—"}
                      </td>
                      <td className={r.changedFields.length ? styles.cellChanged : undefined}>
                        {r.target ? `${r.target.type}${r.target.nullable ? " NULL" : " NOT NULL"}` : "—"}
                      </td>
                      <td>{r.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>

            <details>
              <summary>PK</summary>
              <table className={styles.sideBySideTable}>
                <tbody>
                  <tr className={pkSource !== pkTarget ? styles.cellChanged : undefined}>
                    <td>{pkSource || "—"}</td>
                    <td>{pkTarget || "—"}</td>
                  </tr>
                </tbody>
              </table>
            </details>

            <SectionTable title="Foreign keys" rows={fkRows} render={(fk) => fkKey(fk)} />
            <SectionTable title="Índices" rows={indexRows} render={(ix) => indexKey(ix)} />
            <SectionTable title="Uniques" rows={uniqueRows} render={(u) => uniqueKey(u)} />
            <SectionTable title="Checks" rows={checkRows} render={(c) => c.sqltext} />
          </>
        )}

        {item.object_type === "view" && (
          <details open>
            <summary>Vista</summary>
            {(sourceView?.definition_sha256 == null || targetView?.definition_sha256 == null) && (
              <div className={styles.recency}>Definición no verificable en uno de los dos lados.</div>
            )}
            <div className={styles.wizard}>
              <pre>{sourceView?.definition ?? "—"}</pre>
              <pre>{targetView?.definition ?? "—"}</pre>
            </div>
          </details>
        )}

        {item.object_type === "sequence" && (
          <div className={styles.recency}>
            Secuencia {item.action === "added" ? "presente solo en origen" : "presente solo en destino"}.
          </div>
        )}
      </div>
    </div>
  );
}

export default ObjectDrilldown;

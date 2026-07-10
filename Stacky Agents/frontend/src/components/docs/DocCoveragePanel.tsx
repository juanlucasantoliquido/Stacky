/**
 * DocCoveragePanel.tsx — Plan 109 F5.
 *
 * Pestaña "Cobertura" (solo lectura) de la página Docs: badge de salud
 * documental, tabla de métricas y lista de notas huérfanas. No escribe nada.
 */
import { useMemo } from "react";
import {
  summarizeGraph,
  type DocGraphResponse,
  type DocGraphNode,
  type DocHealth,
} from "../../docs/docGraphModel";
import styles from "./DocCoveragePanel.module.css";

interface Props {
  graph: DocGraphResponse | undefined;
  isLoading: boolean;
  error: string | null;
  onOpenNote?: (node: DocGraphNode) => void;
  /** [ADICIÓN ARQUITECTO] Fuerza re-scan del backend (refresh=1). */
  onRefresh?: () => void;
}

const HEALTH_LABEL: Record<DocHealth["status"], string> = {
  SANA: "Documentación sana",
  INCOMPLETA: "Documentación incompleta",
  FORMATO_NO_OBSIDIAN: "Formato no-Obsidian",
  SIN_DOCS: "Sin documentación",
};

const HEALTH_CLASS: Record<DocHealth["status"], string> = {
  SANA: styles.healthSana,
  INCOMPLETA: styles.healthWarn,
  FORMATO_NO_OBSIDIAN: styles.healthWarn,
  SIN_DOCS: styles.healthBad,
};

export default function DocCoveragePanel({
  graph,
  isLoading,
  error,
  onOpenNote,
  onRefresh,
}: Props) {
  const summary = useMemo(() => (graph ? summarizeGraph(graph) : null), [graph]);

  if (isLoading) {
    return (
      <div className={styles.state}>
        <div className={styles.spinner} />
        <p>Analizando la documentación...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.state}>
        <p className={styles.errorTitle}>No se pudo cargar la cobertura</p>
        <p className={styles.errorDetail}>{error}</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className={styles.state}>
        <p>No hay datos de cobertura para el proyecto activo.</p>
      </div>
    );
  }

  const health = summary.health;
  const rows: [string, number][] = [
    ["Notas", summary.notes],
    ["Aristas totales", summary.totalEdges],
    ["Backlinks totales", summary.totalBacklinks],
    ["Huérfanas", summary.orphanNotes.length],
    ["Fuentes", summary.sources],
    ["Refs a código", summary.codeRefs],
    ["Wikilinks rotos", summary.missing],
  ];
  // Plan 114 — fila "Notas desactualizadas" solo si el payload trae stale_stats (flag ON).
  if (summary.staleNotes !== undefined) {
    rows.push(["Notas desactualizadas", summary.staleNotes]);
  }

  return (
    <section className={styles.panel} aria-label="Cobertura documental">
      <header className={styles.header}>
        {health && (
          <span className={`${styles.badge} ${HEALTH_CLASS[health.status]}`}>
            {HEALTH_LABEL[health.status]}
          </span>
        )}
        {onRefresh && (
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={onRefresh}
            title="Volver a escanear la documentación"
          >
            Recargar
          </button>
        )}
      </header>

      {health && health.reasons.length > 0 && (
        <ul className={styles.reasons}>
          {health.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}

      <table className={styles.metrics}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.orphans}>
        <h3 className={styles.orphansTitle}>
          Notas huérfanas ({summary.orphanNotes.length})
        </h3>
        {summary.orphanNotes.length === 0 ? (
          <p className={styles.orphansEmpty}>
            No hay notas huérfanas: todas están conectadas.
          </p>
        ) : (
          <ul className={styles.orphanList}>
            {summary.orphanNotes.slice(0, 50).map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  className={styles.orphanBtn}
                  onClick={() => onOpenNote?.(node)}
                  disabled={!onOpenNote}
                  title={node.path}
                >
                  {node.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

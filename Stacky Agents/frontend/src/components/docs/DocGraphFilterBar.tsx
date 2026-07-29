/**
 * DocGraphFilterBar.tsx — Plan 268 F1.2.
 *
 * Cascarón DELGADO: cero lógica y cero atributos de estilo en línea (G2 + G8; la
 * prosa evita a propósito escribir ese atributo literal, porque el ratchet de deuda
 * visual cuenta ocurrencias de texto y contaría este comentario). Todas las decisiones
 * (qué opciones existen, cuántos nodos hay) las calculan los helpers puros de
 * docs/graphFilters.ts; acá solo se renderizan y se avisan los clicks.
 */
import type { FilterOptions } from "../../docs/graphFilters";
import type { GraphFilterState, NodeKind, EdgeKind } from "../../docs/graphExplorerState";
import styles from "./DocGraphExplorer.module.css";

interface DocGraphFilterBarProps {
  options: FilterOptions;
  filters: GraphFilterState;
  onToggleSource: (sourceId: string) => void;
  onToggleKind: (kind: NodeKind) => void;
  onToggleEdgeKind: (edgeKind: EdgeKind) => void;
  onSetMinDegree: (n: number) => void;
  onToggleHideOrphans: () => void;
  onToggleOnlyStale: () => void;
  onReset: () => void;
  visibleNodes: number;
  totalNodes: number;
}

function isPristine(f: GraphFilterState): boolean {
  return (
    f.sourceIds.length === 0 &&
    f.kinds.length === 0 &&
    f.edgeKinds.length === 0 &&
    !f.hideOrphans &&
    !f.onlyStale &&
    f.minDegree === 0
  );
}

export default function DocGraphFilterBar({
  options,
  filters,
  onToggleSource,
  onToggleKind,
  onToggleEdgeKind,
  onSetMinDegree,
  onToggleHideOrphans,
  onToggleOnlyStale,
  onReset,
  visibleNodes,
  totalNodes,
}: DocGraphFilterBarProps) {
  return (
    <div className={styles.filterBar}>
      {options.sources.length > 1 ? (
        <fieldset className={styles.group}>
          <legend className={styles.groupLabel}>Fuente</legend>
          {options.sources.map((s) => (
            <button
              key={s.value}
              type="button"
              className={styles.chip}
              aria-pressed={filters.sourceIds.includes(s.value)}
              onClick={() => onToggleSource(s.value)}
              title={`Mostrar solo ${s.label}`}
            >
              {s.label}
              <span className={styles.chipCount}>({s.count})</span>
            </button>
          ))}
        </fieldset>
      ) : null}

      <fieldset className={styles.group}>
        <legend className={styles.groupLabel}>Tipo</legend>
        {options.kinds.map((k) => (
          <button
            key={k.value}
            type="button"
            className={styles.chip}
            aria-pressed={filters.kinds.includes(k.value as NodeKind)}
            onClick={() => onToggleKind(k.value as NodeKind)}
            title={`Mostrar solo ${k.label}`}
          >
            {k.label}
            <span className={styles.chipCount}>({k.count})</span>
          </button>
        ))}
      </fieldset>

      <fieldset className={styles.group}>
        <legend className={styles.groupLabel}>Vista</legend>
        <button
          type="button"
          className={styles.chip}
          aria-pressed={filters.hideOrphans}
          onClick={onToggleHideOrphans}
          title="Ocultar las notas que nadie referencia"
        >
          Ocultar huérfanas
          <span className={styles.chipCount}>({options.orphanCount})</span>
        </button>
        <button
          type="button"
          className={styles.chip}
          aria-pressed={filters.onlyStale}
          onClick={onToggleOnlyStale}
          disabled={options.staleCount === 0}
          title={
            options.staleCount === 0
              ? "No hay notas desactualizadas (o la señal está apagada)"
              : "Mostrar solo las notas desactualizadas"
          }
        >
          Solo desactualizadas
          <span className={styles.chipCount}>({options.staleCount})</span>
        </button>
      </fieldset>

      <details className={`${styles.group} ${styles.more}`}>
        <summary className={styles.moreSummary}>Más filtros</summary>
        <div className={styles.moreBody}>
          <label className={styles.rangeLabel}>
            Grado mínimo: {filters.minDegree}
            <input
              type="range"
              className={styles.range}
              min={0}
              max={Math.max(1, options.maxDegree)}
              step={1}
              value={filters.minDegree}
              onChange={(e) => onSetMinDegree(Number(e.target.value))}
              aria-label="Grado mínimo de conexiones"
            />
          </label>
          {options.edgeKinds.map((k) => (
            <button
              key={k.value}
              type="button"
              className={styles.chip}
              aria-pressed={filters.edgeKinds.includes(k.value as EdgeKind)}
              onClick={() => onToggleEdgeKind(k.value as EdgeKind)}
              title={`Mostrar solo ${k.label}`}
            >
              {k.label}
              <span className={styles.chipCount}>({k.count})</span>
            </button>
          ))}
        </div>
      </details>

      <button
        type="button"
        className={styles.chip}
        onClick={onReset}
        disabled={isPristine(filters)}
        title="Volver a mostrar el grafo completo"
      >
        Limpiar filtros
      </button>

      <span className={styles.counter}>
        Mostrando {visibleNodes} de {totalNodes} nodos
      </span>
    </div>
  );
}

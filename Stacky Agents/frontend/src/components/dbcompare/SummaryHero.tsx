import { DbCompare } from "../../api/endpoints";
import type { CompareRun, DiffItem, Severity, DiffAction } from "./dbcompareTypes";
import { exportFilename, mimeFor, toCsv, toJson } from "./diffExport";
import type { DiffFilters } from "./filterLogic";
import { arcPath, gaugeSweep, severityCounters, actionCounters } from "./svgMath";
import { previousRunDelta } from "./runHistory";
import { relativeTimeEs } from "./relativeTime";
import { safeSummary } from "./summaryShape";
import styles from "./dbcompare.module.css";

const SEVERITY_LABEL: Record<Severity, string> = { danger: "Danger", warn: "Warn", info: "Info" };
const ACTION_LABEL: Record<DiffAction, string> = { added: "Added", removed: "Removed", changed: "Changed" };
const OBJECT_TYPE_LABEL = { table: "tablas", view: "vistas", sequence: "secuencias" } as const;

function scoreColorVar(score: number): string {
  if (score >= 95) return "var(--dbc-added)";
  if (score >= 80) return "var(--dbc-warn)";
  return "var(--dbc-danger)";
}

interface Props {
  run: CompareRun;
  historicalRuns: CompareRun[];
  filters: DiffFilters;
  onToggleSeverity: (s: Severity) => void;
  onToggleAction: (a: DiffAction) => void;
  onNewComparison: () => void;
  /** Plan 176 F8 — los ítems que el operador está VIENDO (ya filtrados) y su
   *  curación, para que el export coincida con la pantalla. */
  filteredItems?: DiffItem[];
  /** Plan 176 F8 — gate de la UX v2 del diff. */
  diffUxV2?: boolean;
}

/**
 * Plan 124 F3 — hero de resultados: gauge de paridad + stat tiles por severidad/acción.
 * Toda la geometría del SVG y los contadores vienen de svgMath.ts (ya testeado); el delta vs.
 * la corrida anterior de runHistory.ts (ADICIÓN ARQUITECTO, ya testeado).
 */
export function SummaryHero({
  run,
  historicalRuns,
  filters,
  onToggleSeverity,
  onToggleAction,
  onNewComparison,
  filteredItems,
  diffUxV2,
}: Props) {
  const diff = run.diff;
  const summary = run.summary;

  /** Exporta lo que se está VIENDO, no el diff entero: si el archivo no coincide
   *  con la pantalla, el operador deja de confiar en los dos. */
  function descargar(ext: "csv" | "json") {
    const items = filteredItems ?? [];
    const contenido = ext === "csv" ? toCsv(items) : toJson(items);
    const url = URL.createObjectURL(new Blob([contenido], { type: mimeFor(ext) }));
    const a = document.createElement("a");
    a.href = url;
    a.download = exportFilename(run.run_id, ext);
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!diff || !summary) return null;

  const sum = safeSummary(summary);
  const score = sum.parity_score;
  const objTypes = sum.by_object_type;
  const sweep = gaugeSweep(score);
  const cx = 100;
  const cy = 100;
  const r = 80;
  const bgArc = arcPath(cx, cy, r, 135, 405);
  const valueArc = arcPath(cx, cy, r, sweep.startDeg, sweep.endDeg);

  const delta = previousRunDelta(run, historicalRuns);
  const deltaCls = !delta ? "" : delta.deltaPoints > 0 ? styles.deltaUp : delta.deltaPoints < 0 ? styles.deltaDown : styles.deltaFlat;
  const deltaSign = delta && delta.deltaPoints > 0 ? "▲" : delta && delta.deltaPoints < 0 ? "▼" : "";

  const copySummary = () => {
    const lines = [
      `Comparación ${run.source_alias} → ${run.target_alias}`,
      `Parity score: ${score}%`,
      ...severityCounters(diff).map((s) => `${SEVERITY_LABEL[s.severity]}: ${s.count}`),
      ...actionCounters(diff).map((a) => `${ACTION_LABEL[a.action]}: ${a.count}`),
    ];
    void navigator.clipboard?.writeText(lines.join("\n"));
  };

  return (
    <div className={styles.hero}>
      <div>
        <svg width={200} height={160} viewBox="0 0 200 200">
          <path d={bgArc} stroke="var(--dbc-unchanged)" strokeWidth={14} fill="none" strokeLinecap="round" />
          <path
            className={styles.gaugeArc}
            d={valueArc}
            stroke={scoreColorVar(score)}
            strokeWidth={14}
            fill="none"
            strokeLinecap="round"
          />
          <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className={styles.gaugeScore}>
            {score}%
          </text>
        </svg>
        {delta && (
          <div className={deltaCls}>
            {deltaSign} {Math.abs(delta.deltaPoints)} pts desde la corrida anterior (
            {relativeTimeEs(delta.previousFinishedAt, new Date().toISOString())})
          </div>
        )}
      </div>

      <div>
        <div className={styles.statTiles}>
          {severityCounters(diff).map((s) => (
            <button
              key={s.severity}
              type="button"
              className={styles.statTile}
              aria-pressed={filters.severities.includes(s.severity)}
              onClick={() => onToggleSeverity(s.severity)}
            >
              <span className={styles.statDot} style={{ background: `var(--dbc-${s.severity})` }} />
              {SEVERITY_LABEL[s.severity]}: {s.count}
            </button>
          ))}
        </div>
        <div className={styles.statTiles}>
          {actionCounters(diff).map((a) => (
            <button
              key={a.action}
              type="button"
              className={styles.statTile}
              aria-pressed={filters.actions.includes(a.action)}
              onClick={() => onToggleAction(a.action)}
            >
              <span className={styles.statDot} style={{ background: `var(--dbc-${a.action})` }} />
              {ACTION_LABEL[a.action]}: {a.count}
            </button>
          ))}
        </div>
        <div className={styles.recency}>
          {(["table", "view", "sequence"] as const)
            .map((t) => `${objTypes[t]} ${OBJECT_TYPE_LABEL[t]}`)
            .join(" · ")}{" "}
          comparados — {sum.objects_unchanged} sin diferencias
        </div>
        <div className={styles.heroActions}>
          <a href={DbCompare.exportUrl(run.run_id)} download className={styles.chip}>
            Exportar .md
          </a>
          {diffUxV2 && filteredItems && (
            <>
              <button onClick={() => descargar("csv")}>CSV</button>
              <button onClick={() => descargar("json")}>JSON</button>
            </>
          )}
          <button onClick={copySummary}>Copiar resumen</button>
          <button onClick={onNewComparison}>Nueva comparación</button>
        </div>
      </div>
    </div>
  );
}

export default SummaryHero;

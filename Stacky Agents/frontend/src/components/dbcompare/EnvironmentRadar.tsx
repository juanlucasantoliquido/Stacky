// Plan 178 F7 — Radar de ambientes (matriz N×N + tendencia + baseline + eventos).
// Autocontenido: si /radar responde 403 (flag OFF) o falla, el componente retorna null.
// CERO estilos inline literales: todo por clases del module.css; el sparkline usa atributos SVG.
import { useCallback, useEffect, useRef, useState } from "react";

import { DbCompare, DbCompareWatch } from "../../api/endpoints";
import type { CompareRun, DbEnvironment, SnapshotMeta } from "./dbcompareTypes";
import {
  buildMatrix,
  cellStateClass,
  formatCellTitle,
  relativeFromIso,
  sparklinePath,
  trendSeries,
} from "./radarLogic";
import type { RadarCell, RadarPayload } from "./radarTypes";
import { DriftEventsPanel } from "./DriftEventsPanel";
import styles from "./dbcompare.module.css";

const STATE_CLASS: Record<"green" | "amber" | "red" | "gray", string> = {
  green: styles.radarCellGreen,
  amber: styles.radarCellAmber,
  red: styles.radarCellRed,
  gray: styles.radarCellGray,
};

interface Props {
  environments: DbEnvironment[];
  runs: CompareRun[];
  onOpenRun: (runId: string) => void;
  onChanged: () => void;
}

export function EnvironmentRadar({ runs, onOpenRun, onChanged }: Props) {
  const [payload, setPayload] = useState<RadarPayload | null>(null);
  const [radarKey, setRadarKey] = useState(0);
  const [selected, setSelected] = useState<{ source: string; target: string } | null>(null);
  const [baselineAlias, setBaselineAlias] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotMeta[]>([]);
  const [chosenSnapshot, setChosenSnapshot] = useState<string>("");
  const [baselineDiffText, setBaselineDiffText] = useState<string | null>(null);
  const [showEvents, setShowEvents] = useState(false);
  const idRef = useRef<number | null>(null);
  const nowMs = Date.now();

  useEffect(() => {
    let active = true;
    const stop = () => {
      if (idRef.current !== null) {
        window.clearInterval(idRef.current);
        idRef.current = null;
      }
    };
    const fetchRadar = () => {
      DbCompareWatch.radar()
        .then((p) => {
          if (active) setPayload(p);
        })
        .catch(() => {
          if (active) {
            setPayload(null);
            stop();
          }
        });
    };
    fetchRadar();
    idRef.current = window.setInterval(fetchRadar, 60_000);
    return () => {
      active = false;
      stop();
    };
  }, [radarKey]);

  useEffect(() => {
    if (!baselineAlias) {
      setSnapshots([]);
      return;
    }
    const env = payload?.environments.find((e) => e.alias === baselineAlias);
    if (env && !env.has_baseline) {
      DbCompare.listSnapshots(baselineAlias)
        .then((r) => setSnapshots(r.snapshots))
        .catch(() => setSnapshots([]));
    }
  }, [baselineAlias, payload]);

  const reload = useCallback(() => {
    setRadarKey((k) => k + 1);
    onChanged();
  }, [onChanged]);

  if (payload === null) return null;

  const meaningful =
    payload.environments.length >= 2 && (payload.cells.length > 0 || payload.watches.length > 0);

  if (!meaningful) {
    return (
      <section className={styles.radarSection}>
        <div className={styles.radarTitle}>Radar de ambientes (esquema)</div>
        <div className={styles.radarHint}>
          El radar aparece cuando hay al menos 2 ambientes registrados y una corrida hecha.
        </div>
      </section>
    );
  }

  const matrix = buildMatrix(payload.environments, payload.cells);
  const selectedCell: RadarCell | null = selected
    ? payload.cells.find(
        (c) => c.source_alias === selected.source && c.target_alias === selected.target,
      ) ?? null
    : null;

  const toggleWatch = (source: string, target: string, watched: boolean) => {
    DbCompareWatch.upsertWatch({ source_alias: source, target_alias: target, enabled: !watched })
      .then(reload)
      .catch(() => undefined);
  };

  const pinBaseline = () => {
    if (!baselineAlias || !chosenSnapshot) return;
    DbCompareWatch.pinBaseline(baselineAlias, chosenSnapshot)
      .then(() => {
        setBaselineAlias(null);
        setChosenSnapshot("");
        reload();
      })
      .catch(() => undefined);
  };

  const unpinBaseline = (alias: string) => {
    DbCompareWatch.unpinBaseline(alias)
      .then(() => {
        setBaselineAlias(null);
        reload();
      })
      .catch(() => undefined);
  };

  const showBaselineDiff = (alias: string) => {
    DbCompareWatch.baselineDiff(alias)
      .then((r) => {
        const sev = r.diff.summary.by_severity;
        setBaselineDiffText(
          `Drift vs baseline de ${alias}: ${sev.danger} danger / ${sev.warn} warn / ${sev.info} info (paridad ${r.diff.summary.parity_score})`,
        );
      })
      .catch(() => setBaselineDiffText(`No se pudo comparar contra el baseline de ${alias}.`));
  };

  const trend = selected ? trendSeries(runs, selected.source, selected.target) : [];

  return (
    <section className={styles.radarSection}>
      <div className={styles.radarHeader}>
        <div>
          <div className={styles.radarTitle}>Radar de ambientes (esquema)</div>
          <div className={styles.radarSubtitle}>
            Matriz de drift por par (origen → destino). Solo esquema; la paridad de datos sigue siendo manual.
          </div>
        </div>
        <button type="button" onClick={() => setShowEvents((v) => !v)}>
          Avisos
          {payload.unread_events > 0 && <span className={styles.unreadBadge}>{payload.unread_events}</span>}
        </button>
      </div>

      <div className={styles.radarGridWrap}>
        <table className={styles.radarGrid}>
          <thead>
            <tr>
              <th className={styles.radarAxis}>origen ／ destino</th>
              {payload.environments.map((env) => (
                <th key={env.alias} className={styles.radarAxis}>
                  <button
                    type="button"
                    onClick={() => {
                      setBaselineAlias((a) => (a === env.alias ? null : env.alias));
                      setBaselineDiffText(null);
                    }}
                  >
                    {env.alias}
                    {env.has_baseline ? <span className={styles.baselinePin}> 📌</span> : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {payload.environments.map((rowEnv, i) => (
              <tr key={rowEnv.alias}>
                <th className={styles.radarAxis}>{rowEnv.alias}</th>
                {payload.environments.map((colEnv, j) => {
                  const cell = matrix[i][j];
                  const stateClass = STATE_CLASS[cellStateClass(cell)];
                  const isSelected =
                    !!selected && selected.source === rowEnv.alias && selected.target === colEnv.alias;
                  const cls = `${styles.radarCell} ${stateClass}${isSelected ? ` ${styles.radarCellSelected}` : ""}`;
                  if (cell === null) {
                    return (
                      <td key={colEnv.alias} className={cls}>
                        {i === j ? "—" : ""}
                      </td>
                    );
                  }
                  return (
                    <td
                      key={colEnv.alias}
                      className={cls}
                      title={formatCellTitle(cell, nowMs)}
                      onClick={() => setSelected({ source: cell.source_alias, target: cell.target_alias })}
                    >
                      {cell.watched ? <span className={styles.radarWatchDot}>👁 </span> : null}
                      {(cell.by_severity.danger || 0) + (cell.by_severity.warn || 0)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedCell && (
        <div className={styles.radarDetail}>
          <div>
            {selectedCell.source_alias} → {selectedCell.target_alias} · paridad{" "}
            {selectedCell.parity_score ?? "?"} · {relativeFromIso(selectedCell.finished_at || "", nowMs)}
          </div>
          {trend.length > 0 && (
            <svg className={styles.radarSparkline} viewBox="0 0 100 24" width="100" height="24">
              <path d={sparklinePath(trend, 100, 24)} />
            </svg>
          )}
          <div className={styles.radarActions}>
            <button type="button" onClick={() => onOpenRun(selectedCell.run_id)}>
              Abrir corrida
            </button>
            <button
              type="button"
              onClick={() => toggleWatch(selectedCell.source_alias, selectedCell.target_alias, selectedCell.watched)}
            >
              {selectedCell.watched ? "Dejar de vigilar" : "Vigilar este par"}
            </button>
          </div>
        </div>
      )}

      {baselineAlias && (
        <div className={styles.radarDetail}>
          {payload.environments.find((e) => e.alias === baselineAlias)?.has_baseline ? (
            <div className={styles.radarActions}>
              <button type="button" onClick={() => showBaselineDiff(baselineAlias)}>
                Ver drift vs baseline
              </button>
              <button type="button" onClick={() => unpinBaseline(baselineAlias)}>
                Despinnear
              </button>
            </div>
          ) : (
            <div className={styles.radarActions}>
              <select value={chosenSnapshot} onChange={(e) => setChosenSnapshot(e.target.value)}>
                <option value="">Elegí un snapshot de {baselineAlias}…</option>
                {snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id} ({s.taken_at})
                  </option>
                ))}
              </select>
              <button type="button" onClick={pinBaseline} disabled={!chosenSnapshot}>
                Pinnear baseline
              </button>
            </div>
          )}
          {baselineDiffText && <div className={styles.radarSubtitle}>{baselineDiffText}</div>}
        </div>
      )}

      {showEvents && (
        <DriftEventsPanel refreshKey={radarKey} onOpenRun={onOpenRun} onChanged={reload} />
      )}
    </section>
  );
}

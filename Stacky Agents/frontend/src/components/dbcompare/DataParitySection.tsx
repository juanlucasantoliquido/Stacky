// Plan 126 F5 — sección "Paridad de datos" dentro de la vista de resultados de
// DbComparePage (Plan 124). Picker de tablas (data-candidates) + lanzamiento
// (data-diff) + grid de diferencias, todo gateado por health.data_diff_enabled
// (flag hija, opt-in doble — ver doc 126 §3).
//
// Sin tests RTL/jsdom (gap estructural del repo, ver
// gotcha-rtl-jsdom-structural-gap): la lógica de negocio (selección con cap,
// filas del grid, contadores, filtro) vive en dataDiffLogic.ts, 100% pura y
// testeada con vitest. Este archivo es JSX + fetch/polling, verificado con
// tsc --noEmit.
import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { CompareRun, DataDiffRunState } from "./dbcompareTypes";
import {
  buildDataGridRows,
  candidateFilter,
  candidateKey,
  dataCounters,
  parseCandidateKey,
  toggleTableSelection,
  type DataCandidate,
  type DataDiff,
} from "./dataDiffLogic";
import { isTerminal, nextPollDelayMs } from "./useCompareRun";
import { DataMaskingBar } from "./DataMaskingBar";
import styles from "./dbcompare.module.css";

const MAX_TABLES = 20;

interface Props {
  run: CompareRun;
  onRunUpdate: (run: CompareRun) => void;
}

export function DataParitySection({ run, onRunUpdate }: Props) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<DataCandidate[] | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);

  const dataDiff = run.data_diff ?? null;

  // Candidatas: 1 fetch al abrir, mientras no haya un data_diff ya lanzado.
  useEffect(() => {
    if (!open || candidates || dataDiff) return;
    DbCompare.dataCandidates(run.run_id)
      .then((r) => setCandidates(r.candidates))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [open, run.run_id, candidates, dataDiff]);

  // Polling del sub-estado data_diff mientras esté "running" (mismo backoff que
  // useCompareRun, doc 124 §F1 — el run principal ya está "done" acá, por eso
  // no se reusa el hook directo: se polea el mismo GET /runs/<id> a mano).
  useEffect(() => {
    if (!dataDiff || isTerminal(dataDiff.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const startedAt = Date.now();

    const poll = async (): Promise<void> => {
      try {
        const fresh = await DbCompare.getRun(run.run_id);
        if (cancelled) return;
        onRunUpdate(fresh);
        if (fresh.data_diff && !isTerminal(fresh.data_diff.status)) {
          timer = setTimeout(poll, nextPollDelayMs(Date.now() - startedAt));
        }
      } catch {
        // Silencioso: si el operador reabre la sección, se reintenta solo.
      }
    };
    timer = setTimeout(poll, nextPollDelayMs(0));
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataDiff?.status, run.run_id]);

  const filtered = candidates ? candidateFilter(candidates, search) : [];

  const handleStart = async () => {
    setLaunching(true);
    setError(null);
    const tables = [...selected].map(parseCandidateKey);
    try {
      await DbCompare.startDataDiff(run.run_id, tables);
      const fresh = await DbCompare.getRun(run.run_id);
      onRunUpdate(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLaunching(false);
    }
  };

  if (!open) {
    return (
      <section className={styles.scriptsSection}>
        <button onClick={() => setOpen(true)}>Comparar datos…</button>
      </section>
    );
  }

  return (
    <section className={styles.scriptsSection}>
      <h2>Paridad de datos</h2>
      {error && <div className={styles.errorBanner}>{error}</div>}

      {!dataDiff && (
        <>
          <div className={styles.runIdRow}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar tabla o schema…"
            />
          </div>
          <p>{selected.size}/{MAX_TABLES} seleccionadas</p>
          <ul>
            {filtered.map((c) => {
              const key = candidateKey(c.schema, c.table);
              return (
                <li key={key}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.has(key)}
                      disabled={!c.comparable}
                      onChange={() => setSelected((prev) => toggleTableSelection(prev, key, MAX_TABLES))}
                    />
                    {c.schema}.{c.table}
                    {!c.comparable && <em> — {c.reason}</em>}
                    {c.row_count_source != null && c.row_count_target != null && (
                      <span>
                        {" "}
                        ({c.row_count_source} / {c.row_count_target} filas)
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
          <button onClick={handleStart} disabled={selected.size === 0 || launching}>
            {launching ? "Iniciando…" : "Comparar datos"}
          </button>
        </>
      )}

      {dataDiff && dataDiff.status === "running" && <p>{dataDiff.phase}</p>}
      {dataDiff && dataDiff.status === "error" && <div className={styles.errorBanner}>{dataDiff.error}</div>}
      {dataDiff && dataDiff.status === "done" && (
        <DataMaskingBar
          tables={dataDiff.tables}
          onChanged={() => DbCompare.getRun(run.run_id).then(onRunUpdate).catch(() => undefined)}
        />
      )}
      {dataDiff && dataDiff.status === "done" && <DataDiffTables tables={dataDiff.tables} />}
    </section>
  );
}

function DataDiffTables({ tables }: { tables: DataDiffRunState["tables"] }) {
  const entries = Object.entries(tables);
  if (entries.length === 0) return <p>Sin tablas comparadas.</p>;
  return (
    <>
      {entries.map(([key, result]) => (
        <details key={key} open>
          <summary>{key}</summary>
          {"error" in result ? (
            <div className={styles.errorBanner}>{result.error}</div>
          ) : (
            <DataDiffTable diff={result} />
          )}
        </details>
      ))}
    </>
  );
}

function DataDiffTable({ diff }: { diff: DataDiff }) {
  const counters = dataCounters(diff);
  const rows = buildDataGridRows(diff);
  return (
    <>
      <p>
        +{counters.inserts} faltantes · ~{counters.updates} difieren · −{counters.deletes} sobrantes
        {diff.truncated && <strong> (truncado)</strong>}
      </p>
      <table className={styles.sideBySideTable}>
        <thead>
          <tr>
            <th>PK</th>
            <th>Columna</th>
            <th>Origen</th>
            <th>Destino</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) =>
            row.cells.map((cell, i) => (
              <tr
                key={`${row.pk}-${cell.col}`}
                className={
                  row.kind === "only_source" ? styles.rowAdded : row.kind === "only_target" ? styles.rowRemoved : undefined
                }
              >
                {i === 0 && <td rowSpan={row.cells.length}>{row.pk}</td>}
                <td>{cell.col}</td>
                <td className={cell.changed ? styles.cellChanged : undefined}>{cell.source ?? "NULL"}</td>
                <td className={cell.changed ? styles.cellChanged : undefined}>{cell.target ?? "NULL"}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </>
  );
}

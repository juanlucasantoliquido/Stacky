import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { CompareRun, DbCompareHealth, DbEnvironment, DbSnapshot, DiffAction, DiffItem, Severity } from "./dbcompareTypes";
import { EMPTY_FILTERS, filterDiffItems, type DiffFilters } from "./filterLogic";
import { buildSnapshotCounts } from "./snapshotCounts";
import { EnvironmentsPanel } from "./EnvironmentsPanel";
import { DbCompareSettingsSection } from "./DbCompareSettingsSection";
import { ScriptsPanel } from "./ScriptsPanel";
import { CompareWizard } from "./CompareWizard";
import { RunProgress } from "./RunProgress";
import { SummaryHero } from "./SummaryHero";
import { FiltersBar } from "./FiltersBar";
import { DiffTreemap } from "./DiffTreemap";
import { DiffList } from "./DiffList";
import { ObjectDrilldown } from "./ObjectDrilldown";
import { RunsTimeline } from "./RunsTimeline";
import { DataParitySection } from "./DataParitySection";
import styles from "./dbcompare.module.css";

type ViewState = "wizard" | "progress" | "results";

/**
 * Plan 122 F5 — tab "Comparador BD": header con estado de drivers + gestión de ambientes.
 * Plan 124 — sección inmersiva completa: wizard -> progreso -> hero -> filtros ->
 * treemap/lista -> drill-down, con historial de corridas 1-click.
 */
export function DbComparePage() {
  const [health, setHealth] = useState<DbCompareHealth | null>(null);
  const [runIdInput, setRunIdInput] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [environments, setEnvironments] = useState<DbEnvironment[]>([]);
  const [runs, setRuns] = useState<CompareRun[]>([]);
  const [view, setView] = useState<ViewState>("wizard");
  const [activeRun, setActiveRun] = useState<CompareRun | null>(null);
  const [filters, setFilters] = useState<DiffFilters>(EMPTY_FILTERS);
  const [displayMode, setDisplayMode] = useState<"map" | "list">("map");
  const [selectedItem, setSelectedItem] = useState<DiffItem | null>(null);
  const [sourceSnapshot, setSourceSnapshot] = useState<DbSnapshot | null>(null);
  const [targetSnapshot, setTargetSnapshot] = useState<DbSnapshot | null>(null);

  useEffect(() => {
    DbCompare.health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const reloadEnvironments = () => {
    DbCompare.listEnvironments()
      .then((r) => setEnvironments(r.environments))
      .catch(() => setEnvironments([]));
  };
  const reloadRuns = () => {
    DbCompare.listRuns(20)
      .then((r) => setRuns(r.runs))
      .catch(() => setRuns([]));
  };

  useEffect(() => {
    reloadEnvironments();
    reloadRuns();
  }, []);

  // Snapshots completos: 1 fetch por lado cuando hay un run "done" con resultados que mostrar
  // (treemap y drill-down comparten el mismo cache, doc §F4/§F5).
  useEffect(() => {
    setSourceSnapshot(null);
    setTargetSnapshot(null);
    if (!activeRun || activeRun.status !== "done") return;
    if (activeRun.source_snapshot_id) {
      DbCompare.getSnapshot(activeRun.source_snapshot_id)
        .then(setSourceSnapshot)
        .catch(() => setSourceSnapshot(null));
    }
    if (activeRun.target_snapshot_id) {
      DbCompare.getSnapshot(activeRun.target_snapshot_id)
        .then(setTargetSnapshot)
        .catch(() => setTargetSnapshot(null));
    }
  }, [activeRun?.run_id, activeRun?.status]);

  const handleLaunched = (run: CompareRun) => {
    setActiveRun(run);
    setView("progress");
  };

  const handleRunDone = (run: CompareRun) => {
    setActiveRun(run);
    setFilters(EMPTY_FILTERS);
    setView("results");
    reloadRuns();
  };

  const handleSelectHistoricalRun = async (run: CompareRun) => {
    try {
      const full = await DbCompare.getRun(run.run_id);
      setActiveRun(full);
      setFilters(EMPTY_FILTERS);
      setView(full.status === "running" ? "progress" : "results");
    } catch {
      // Sin cambios si falla: el usuario sigue viendo lo que tenía.
    }
  };

  const handleNewComparison = () => {
    setActiveRun(null);
    setView("wizard");
  };

  const toggleSeverity = (s: Severity) =>
    setFilters((f) => ({ ...f, severities: f.severities.includes(s) ? f.severities.filter((x) => x !== s) : [...f.severities, s] }));
  const toggleAction = (a: DiffAction) =>
    setFilters((f) => ({ ...f, actions: f.actions.includes(a) ? f.actions.filter((x) => x !== a) : [...f.actions, a] }));

  const missingDrivers = health ? Object.entries(health.drivers).filter(([, info]) => !info.available) : [];
  const diff = activeRun?.diff ?? null;
  const filteredItems = diff ? filterDiffItems(diff.items, filters) : [];
  const snapshotCounts = buildSnapshotCounts(sourceSnapshot, targetSnapshot);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Comparador de BD entre ambientes</h1>
        <p className={styles.subtitle}>
          Registrá ambientes de BD (solo lectura), tomá snapshots de esquema y compará
          drift entre ellos. Stacky genera, nunca ejecuta.
        </p>
      </header>

      {missingDrivers.length > 0 && (
        <div className={styles.driverWarning}>
          {missingDrivers.map(([engine, info]) => (
            <div key={engine} className={styles.driverWarningRow}>
              <strong>{engine}</strong>: falta el driver <code>{info.module}</code>.
              <br />
              Instalalo con: <code>{info.install_hint}</code>
            </div>
          ))}
        </div>
      )}

      <DbCompareSettingsSection />

      <RunsTimeline runs={runs} activeRunId={activeRun?.run_id ?? null} onSelectRun={handleSelectHistoricalRun} />

      {view === "wizard" && <CompareWizard environments={environments} onLaunched={handleLaunched} />}

      {view === "progress" && activeRun && (
        <RunProgress
          runId={activeRun.run_id}
          sourceAlias={activeRun.source_alias}
          targetAlias={activeRun.target_alias}
          mode={activeRun.mode}
          onDone={handleRunDone}
        />
      )}

      {view === "results" && activeRun && diff && (
        <>
          <SummaryHero
            run={activeRun}
            historicalRuns={runs}
            filters={filters}
            onToggleSeverity={toggleSeverity}
            onToggleAction={toggleAction}
            onNewComparison={handleNewComparison}
          />
          <FiltersBar filters={filters} onChange={setFilters} filteredCount={filteredItems.length} totalCount={diff.items.length} />
          <div>
            <button onClick={() => setDisplayMode("map")} aria-pressed={displayMode === "map"}>
              Mapa
            </button>
            <button onClick={() => setDisplayMode("list")} aria-pressed={displayMode === "list"}>
              Lista
            </button>
          </div>
          {displayMode === "map" ? (
            <DiffTreemap diff={diff} snapshotCounts={snapshotCounts} onSelectItem={setSelectedItem} />
          ) : (
            <DiffList items={filteredItems} onSelectItem={setSelectedItem} />
          )}
          {health?.data_diff_enabled && <DataParitySection run={activeRun} onRunUpdate={setActiveRun} />}
        </>
      )}

      {view === "results" && activeRun && !diff && (
        <div className={styles.emptyState}>
          {activeRun.status === "error" ? activeRun.error : "Esta corrida no tiene diferencias para mostrar."}
        </div>
      )}

      {selectedItem && (
        <ObjectDrilldown
          item={selectedItem}
          sourceSnapshot={sourceSnapshot}
          targetSnapshot={targetSnapshot}
          onClose={() => setSelectedItem(null)}
        />
      )}

      <EnvironmentsPanel keyringAvailable={health?.keyring_available ?? true} />

      <section className={styles.scriptsSection}>
        <h2>Scripts de paridad (Plan 125)</h2>
        <p className={styles.subtitle}>
          Pegá el ID de una corrida ya terminada (<code>done</code>) para generar y ver sus
          scripts de paridad + backups pareados 1:1. El listado visual de corridas (Plan 124)
          todavía no está montado acá; por ahora se busca por ID.
        </p>
        <div className={styles.runIdRow}>
          <input
            value={runIdInput}
            onChange={(e) => setRunIdInput(e.target.value)}
            placeholder="run_20260714T120000Z_DEV_vs_TEST"
          />
          <button
            onClick={() => setActiveRunId(runIdInput.trim() || null)}
            disabled={!runIdInput.trim()}
          >
            Ver scripts
          </button>
        </div>
        {activeRunId && <ScriptsPanel key={activeRunId} runId={activeRunId} />}
      </section>
    </div>
  );
}

export default DbComparePage;

import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { CompareRun, DbCompareHealth, DbEnvironment, DbSnapshot, DiffAction, DiffItem, Severity } from "./dbcompareTypes";
import { EMPTY_FILTERS, filterDiffItems, type DiffFilters } from "./filterLogic";
import { buildSnapshotCounts } from "./snapshotCounts";
import { EnvironmentsPanel } from "./EnvironmentsPanel";
import { DbCompareSettingsSection } from "./DbCompareSettingsSection";
import { EnvironmentRadar } from "./EnvironmentRadar";
import { DemoSandboxPanel } from "./DemoSandboxPanel";
import { ScriptsPanel } from "./ScriptsPanel";
import { CompareWizard } from "./CompareWizard";
import { RunProgress } from "./RunProgress";
import { SummaryHero } from "./SummaryHero";
import GatesPanel from "./GatesPanel";
import {
  summarizeTriage,
  type TriageDecision,
  type TriageDoc,
} from "./triageLogic";
import { FiltersBar } from "./FiltersBar";
import { DiffTreemap } from "./DiffTreemap";
import { DiffList } from "./DiffList";
import { ObjectDrilldown } from "./ObjectDrilldown";
import { RunsTimeline } from "./RunsTimeline";
import { DataParitySection } from "./DataParitySection";
import { EnvSetupWizard } from "./EnvSetupWizard";
import { MigrationPanel } from "./MigrationPanel";
import { shouldShowEmptyCta, shouldNudgeAddMore } from "./envPlacementLogic";
import { RepoCoveragePanel } from "./RepoCoveragePanel";
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
  // Plan 157 F5/F6 — wizard de alta en contexto + remount de la lista tras crear.
  const [showWizard, setShowWizard] = useState(false);
  const [envRefreshToken, setEnvRefreshToken] = useState(0);

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

  // Plan 157 — flags de UX (default ON en backend; con las 3 en false la página
  // queda idéntica a main).
  const configInPlace = health?.config_in_place_enabled ?? false;
  const webconfigImport = health?.webconfig_import_enabled ?? false;
  const migrationPanel = health?.migration_panel_enabled ?? false;
  // Plan 176 F2 — curación del diff. Se carga al entrar en resultados de una
  // corrida `done`; con la flag OFF no se pide nada y la vista queda igual.
  const triageEnabled = health?.triage_enabled ?? false;
  const [triage, setTriage] = useState<TriageDoc | null>(null);

  useEffect(() => {
    if (!triageEnabled || view !== "results" || !activeRun || activeRun.status !== "done") {
      setTriage(null);
      return;
    }
    let vigente = true;
    DbCompare.getTriage(activeRun.run_id)
      .then((doc) => {
        if (vigente) setTriage(doc as TriageDoc);
      })
      .catch(() => {
        // Sin triage la lista sigue siendo usable: no se rompe la vista.
        if (vigente) setTriage(null);
      });
    return () => {
      vigente = false;
    };
  }, [triageEnabled, view, activeRun]);

  async function decidirItem(itemKey: string, decision: TriageDecision, note?: string) {
    if (!activeRun) return;
    try {
      const doc = await DbCompare.putTriageItem(activeRun.run_id, {
        item_key: itemKey,
        decision,
        note,
      });
      setTriage(doc as TriageDoc);
    } catch {
      // Una decisión que no se pudo guardar no puede dejar la UI mintiendo:
      // se relee el estado real del servidor.
      DbCompare.getTriage(activeRun.run_id)
        .then((doc) => setTriage(doc as TriageDoc))
        .catch(() => setTriage(null));
    }
  }

  const handleEnvCreated = () => {
    reloadEnvironments();
    setEnvRefreshToken((t) => t + 1); // fuerza remount de EnvironmentsPanel (estado propio)
    setShowWizard(false);
  };

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

      {/* Plan 157 F5 — gestión de ambientes ELEVADA al tope, con CTA de estado vacío
          y wizard guiado. Gateada por config_in_place_enabled: con OFF, la página
          queda como en main (EnvironmentsPanel al fondo). */}
      {configInPlace && (
        <section className={styles.environmentsPanel}>
          <h2>Bases de datos configuradas</h2>
          {shouldShowEmptyCta(environments, configInPlace) && !showWizard && (
            <button className={styles.emptyCta} onClick={() => setShowWizard(true)}>
              ➕ Agregar una base de datos para empezar
            </button>
          )}
          {shouldNudgeAddMore(environments) && (
            <p className={styles.nudge}>
              Necesitás al menos 2 ambientes para comparar — agregá otro.
            </p>
          )}
          {environments.length > 0 && !showWizard && (
            <button onClick={() => setShowWizard(true)}>➕ Agregar base de datos</button>
          )}
          {showWizard && (
            <EnvSetupWizard
              webconfigImportEnabled={webconfigImport}
              onCreated={handleEnvCreated}
              onCancel={() => setShowWizard(false)}
            />
          )}
          <EnvironmentsPanel key={envRefreshToken} keyringAvailable={health?.keyring_available ?? true} />
        </section>
      )}
      <DemoSandboxPanel environments={environments} onChanged={() => { reloadEnvironments(); reloadRuns(); }} />

      <DbCompareSettingsSection />

      <EnvironmentRadar
        environments={environments}
        runs={runs}
        onOpenRun={(runId: string) => { void handleSelectHistoricalRun({ run_id: runId } as CompareRun); }}
        onChanged={reloadRuns}
      />

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
            filteredItems={filteredItems}
            triage={triage}
          />
          {/* Plan 176 F2 — resumen de curacion: cuanto falta decidir de un
              vistazo. Informativo; decidir se hace en cada fila. */}
          {triageEnabled && (
            <div className={styles.triageSummary}>
              {(() => {
                const r = summarizeTriage(triage, diff.items.length);
                return (
                  <>
                    <span>{r.confirmado} confirmados</span>
                    <span>{r.excluido} excluidos</span>
                    <span>{r.pendiente} sin decidir</span>
                    {r.excluido > 0 && (
                      <a href={DbCompare.triageExclusionsUrl(activeRun.run_id)} download>
                        Descargar exclusiones
                      </a>
                    )}
                  </>
                );
              })()}
            </div>
          )}
          {/* Plan 176 F5 — inmediatamente despues del hero, como manda el plan:
              lo primero que hay que saber antes de generar scripts es si algo
              bloquea la migracion. Se auto-oculta con la flag OFF. */}
          <GatesPanel
            runId={activeRun.run_id}
            runStatus={activeRun.status}
            enabled={health?.gates_enabled ?? false}
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
            <DiffList
              items={filteredItems}
              onSelectItem={setSelectedItem}
              triage={triage}
              triageEnabled={triageEnabled}
              onDecide={decidirItem}
            />
          )}
          {health?.data_diff_enabled && <DataParitySection run={activeRun} onRunUpdate={setActiveRun} />}
          <RepoCoveragePanel runId={activeRun.run_id} />
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
          triage={triage}
          triageEnabled={triageEnabled}
          onDecide={decidirItem}
        />
      )}

      {/* Plan 157 F5 — con config_in_place OFF, la gestión de ambientes queda al
          fondo como en main. */}
      {!configInPlace && <EnvironmentsPanel keyringAvailable={health?.keyring_available ?? true} />}

      {/* Plan 157 F6 — Panel de Migración persistente (flag ON) vs. bloque legacy de
          "pegá el run_id" (flag OFF, backward-compatible con main). */}
      {migrationPanel ? (
        <MigrationPanel runs={runs} />
      ) : (
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
      )}
    </div>
  );
}

export default DbComparePage;

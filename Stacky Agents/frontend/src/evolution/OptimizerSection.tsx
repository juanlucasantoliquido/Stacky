// Plan 169 F5 — sección "Optimizador evolutivo" del Centro de Evolución.
// TODO estilo va en el .module.css (G6: cero style inline). El ÚNICO polling es el de
// una corrida EN CURSO: setTimeout encadenado con tope duro RUN_POLL_MAX y stop en
// terminal/unmount (G9: nunca un temporizador periódico). Con la flag OFF no renderiza nada.
import { useCallback, useEffect, useRef, useState } from "react";
import { EvolutionOptimizer } from "../api/endpoints";
import { Button, Card, SectionHeader, StatusChip, Field, Select } from "../components/ui";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import ConfirmButton from "../components/ConfirmButton";
import Toast, { type ToastState } from "../components/Toast";
import { formatTokens, formatDateTime, formatTime } from "../services/format";
import {
  type OptimizerTargetDto,
  type OptimizationRunDto,
  type ArchiveEntryDto,
  RUN_POLL_MS,
  RUN_POLL_MAX,
  runStatusTone,
  runStatusLabel,
  verdictTone,
  verdictLabel,
  generatorLabel,
  isTerminal,
  lineageRows,
  improvementDisplay,
} from "./optimizerModel";
import styles from "./OptimizerSection.module.css";

interface HealthDto {
  ok: boolean;
  flag_enabled: boolean;
  generator_mode: string;
  generator_ready: boolean;
  harness_enabled: boolean;
}

interface LessonDto {
  text: string;
  outcome: string;
  delta: number | null;
}

const RUNTIME_OPTS = ["github_copilot", "claude_code_cli", "codex_cli"] as const;

export default function OptimizerSection() {
  const [phase, setPhase] = useState<"loading" | "hidden" | "error" | "ready">("loading");
  const [health, setHealth] = useState<HealthDto | null>(null);
  const [targets, setTargets] = useState<OptimizerTargetDto[]>([]);
  const [runs, setRuns] = useState<OptimizationRunDto[]>([]);
  const [activeRun, setActiveRun] = useState<OptimizationRunDto | null>(null);
  const [runtime, setRuntime] = useState<string>("github_copilot");
  const [busyTarget, setBusyTarget] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [archiveByRun, setArchiveByRun] = useState<Record<string, ArchiveEntryDto[]>>({});
  const [lessons, setLessons] = useState<LessonDto[] | null>(null);

  const pollRef = useRef<{ stop: boolean; count: number }>({ stop: false, count: 0 });

  const loadOverview = useCallback(async () => {
    const [t, r] = await Promise.all([EvolutionOptimizer.targets(), EvolutionOptimizer.runs(10)]);
    if (t.ok) setTargets((t.data.targets ?? []) as OptimizerTargetDto[]);
    if (r.ok) setRuns((r.data.runs ?? []) as OptimizationRunDto[]);
  }, []);

  useEffect(() => {
    let alive = true;
    const ref = pollRef.current;
    (async () => {
      try {
        const h = (await EvolutionOptimizer.health()) as HealthDto;
        if (!alive) return;
        if (!h.flag_enabled) {
          setPhase("hidden");
          return;
        }
        setHealth(h);
        await loadOverview();
        if (alive) setPhase("ready");
      } catch {
        if (alive) setPhase("error");
      }
    })();
    return () => {
      alive = false;
      ref.stop = true; // unmount corta el ciclo de polling
    };
  }, [loadOverview]);

  const pollActiveRun = useCallback(
    (runId: string) => {
      if (pollRef.current.stop || pollRef.current.count >= RUN_POLL_MAX) return;
      pollRef.current.count += 1;
      window.setTimeout(async () => {
        if (pollRef.current.stop) return;
        const res = await EvolutionOptimizer.getRun(runId);
        if (!res.ok) return;
        const run = res.data.run as OptimizationRunDto;
        setActiveRun(run);
        if (isTerminal(run.status)) {
          await loadOverview();
        } else {
          pollActiveRun(runId);
        }
      }, RUN_POLL_MS);
    },
    [loadOverview],
  );

  const onOptimize = useCallback(
    async (target: OptimizerTargetDto) => {
      setBusyTarget(target.target_ref);
      const runtimeArg = health?.generator_mode === "runtime" ? runtime : null;
      const res = await EvolutionOptimizer.run(target.target_ref, runtimeArg, true);
      setBusyTarget(null);
      if (res.status === 202 && res.data.run) {
        const run = res.data.run as OptimizationRunDto;
        setActiveRun(run);
        pollRef.current = { stop: false, count: 0 };
        if (!isTerminal(run.status)) pollActiveRun(run.id);
        else await loadOverview();
      } else {
        setToast({
          variant: "warning",
          body: res.data.message || res.data.error || "No se pudo iniciar la corrida",
        });
      }
    },
    [health, runtime, pollActiveRun, loadOverview],
  );

  const onCancel = useCallback(async (runId: string) => {
    const res = await EvolutionOptimizer.cancel(runId);
    if (!res.ok) setToast({ variant: "warning", body: res.data.error || "No se pudo cancelar" });
  }, []);

  const toggleArchive = useCallback(
    async (runId: string) => {
      if (archiveByRun[runId]) {
        setArchiveByRun((prev) => {
          const next = { ...prev };
          delete next[runId];
          return next;
        });
        return;
      }
      const res = await EvolutionOptimizer.archive({ run_id: runId });
      if (res.ok) {
        setArchiveByRun((prev) => ({ ...prev, [runId]: (res.data.entries ?? []) as ArchiveEntryDto[] }));
      }
    },
    [archiveByRun],
  );

  const toggleLessons = useCallback(async () => {
    if (lessons !== null) {
      setLessons(null);
      return;
    }
    const aspect = activeRun?.aspect_key ?? targets[0]?.aspect_key ?? "";
    if (!aspect) {
      setLessons([]);
      return;
    }
    const res = await EvolutionOptimizer.lessons(aspect, 20);
    setLessons(res.ok ? ((res.data.lessons ?? []) as LessonDto[]) : []);
  }, [lessons, activeRun, targets]);

  if (phase === "hidden") return null;

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Optimizador evolutivo"
        subtitle="Genera variantes de un prompt de agente, las mide con el arnés de fitness y te propone la mejor. Vos aprobás siempre."
      />

      {phase === "loading" ? <SkeletonList rows={4} /> : null}

      {phase === "error" ? (
        <Card>
          <div className={styles.banner}>
            <span>No se pudo cargar el optimizador.</span>
            <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
              Reintentar
            </Button>
          </div>
        </Card>
      ) : null}

      {phase === "ready" ? (
        <>
          {health && !health.harness_enabled ? (
            <div className={styles.warnRow}>
              <StatusChip tone="warning">Arnés de fitness deshabilitado — el optimizador no puede correr</StatusChip>
            </div>
          ) : null}

          {health?.generator_mode === "runtime" ? (
            <div className={styles.runtimePicker}>
              <Field label="Runtime generador">
                {(ctl) => (
                  <Select {...ctl} value={runtime} onChange={(e) => setRuntime(e.target.value)}>
                    {RUNTIME_OPTS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          ) : null}

          {targets.length === 0 ? (
            <EmptyState
              title="Sin prompts optimizables"
              message="Agregá agentes en backend/Stacky/agents/ para poder optimizarlos."
            />
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Prompt</th>
                    <th>Aspecto</th>
                    <th>Casos</th>
                    <th>Último score</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {targets.map((t) => (
                    <tr key={t.target_ref}>
                      <td>{t.target_ref}</td>
                      <td className={styles.muted}>{t.aspect_key}</td>
                      <td>{t.cases_enabled}</td>
                      <td>{t.last_score ?? "—"}</td>
                      <td>
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={
                            busyTarget !== null ||
                            (health ? !health.harness_enabled || !health.generator_ready : true)
                          }
                          onClick={() => onOptimize(t)}
                        >
                          Optimizar
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeRun ? (
            <Card>
              <div className={styles.runCard}>
                <div className={styles.runMeta}>
                  <StatusChip tone={runStatusTone(activeRun.status)}>
                    {runStatusLabel(activeRun.status)}
                  </StatusChip>
                  <span className={styles.muted}>{generatorLabel(activeRun.generator)}</span>
                  <span>
                    variante {activeRun.variants_done}/{activeRun.variants_planned}
                  </span>
                  <span>
                    {formatTokens(activeRun.budget.tokens_est_in + activeRun.budget.tokens_est_out)} tokens
                  </span>
                  <span>{improvementDisplay(activeRun.base?.score ?? null, activeRun.winner?.score ?? null)}</span>
                  {activeRun.status === "running" ? (
                    <ConfirmButton
                      label="Cancelar"
                      confirmLabel="⚠ Confirmar cancelación"
                      onConfirm={() => onCancel(activeRun.id)}
                    />
                  ) : null}
                </div>
                {activeRun.proposal_id ? (
                  <a className={styles.proposalLink} href={`/evolution?proposal=${activeRun.proposal_id}`}>
                    Ver propuesta emitida
                  </a>
                ) : null}
                <ul className={styles.steps}>
                  {activeRun.steps.slice(-10).map((s, i) => (
                    <li key={`${s.ts}-${i}`} className={styles.step}>
                      <span className={styles.stepTime}>{formatTime(s.ts)}</span>
                      <span>{s.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          ) : null}

          <div className={styles.collapsibles}>
            <button
              type="button"
              className={styles.toggle}
              onClick={() => setShowHistory((v) => !v)}
            >
              {showHistory ? "▾" : "▸"} Historial de corridas ({runs.length})
            </button>
            {showHistory ? (
              runs.length === 0 ? (
                <EmptyState title="Sin corridas todavía" message="Elegí un prompt y tocá Optimizar." />
              ) : (
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Prompt</th>
                        <th>Estado</th>
                        <th>Score base → ganadora</th>
                        <th>Propuesta</th>
                        <th>Fecha</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.id}>
                          <td>{r.target_ref}</td>
                          <td>
                            <StatusChip tone={runStatusTone(r.status)}>{runStatusLabel(r.status)}</StatusChip>
                          </td>
                          <td>{improvementDisplay(r.base?.score ?? null, r.winner?.score ?? null)}</td>
                          <td>
                            {r.proposal_id ? (
                              <a href={`/evolution?proposal=${r.proposal_id}`}>Ver</a>
                            ) : (
                              <span className={styles.muted}>—</span>
                            )}
                          </td>
                          <td className={styles.muted}>{formatDateTime(r.finished_at ?? r.started_at)}</td>
                          <td>
                            <Button variant="ghost" size="sm" onClick={() => toggleArchive(r.id)}>
                              {archiveByRun[r.id] ? "Ocultar lineage" : "Lineage"}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : null}

            {Object.entries(archiveByRun).map(([runId, entries]) => (
              <div key={runId} className={styles.lineage}>
                {lineageRows(entries).map(({ entry, depth }) => (
                  <div
                    key={entry.id}
                    className={depth === 1 ? `${styles.lineageRow} ${styles.depth1}` : styles.lineageRow}
                  >
                    <StatusChip tone={verdictTone(entry.verdict)}>{verdictLabel(entry.verdict)}</StatusChip>
                    <span>{entry.fitness?.score ?? "—"}</span>
                    <span className={styles.muted}>{formatTokens(entry.cost_proxy)} tokens</span>
                    {entry.mutation_lesson ? (
                      <span className={styles.subtext}>{entry.mutation_lesson}</span>
                    ) : null}
                    {entry.invalid_reason ? (
                      <span className={styles.subtext}>{entry.invalid_reason}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            ))}

            <button type="button" className={styles.toggle} onClick={toggleLessons}>
              {lessons !== null ? "▾" : "▸"} Lecciones de mutación
            </button>
            {lessons !== null ? (
              lessons.length === 0 ? (
                <p className={styles.muted}>Sin lecciones todavía.</p>
              ) : (
                <ul className={styles.lessonList}>
                  {lessons.map((l, i) => (
                    <li key={i}>
                      ({l.outcome}, Δ{l.delta ?? "—"}) {l.text}
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
        </>
      ) : null}

      {toast ? <Toast toast={toast} onClose={() => setToast(null)} /> : null}
    </div>
  );
}

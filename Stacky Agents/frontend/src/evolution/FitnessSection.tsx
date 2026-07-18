// Plan 168 F6 — sección "Fitness de agentes" del Centro de Evolución.
// TODO estilo va en el .module.css (G6: cero style inline). CERO pollers (G9):
// carga on-mount + botones + refresh post-acción. Con la flag OFF no renderiza nada.
import { useCallback, useEffect, useState } from "react";
import { EvolutionFitness } from "../api/endpoints";
import { Button, Card, SectionHeader, StatusChip, Spinner, Field, Input, Select } from "../components/ui";
import type { StatusTone } from "../components/ui";
import ConfirmButton from "../components/ConfirmButton";
import SkeletonList from "../components/SkeletonList";
import Toast, { type ToastState } from "../components/Toast";
import { firstErrorFieldId } from "../components/ui";
import {
  type ScorecardDto,
  type EvalCaseDto,
  type SignalLevel,
  type JudgeCheckStatus,
  aspectLabel,
  scoreDisplay,
  gateLabel,
  deltaDisplay,
  deltaTone,
  levelLabel,
  levelTone,
  judgeCheckLabel,
} from "./fitnessModel";
import styles from "./FitnessSection.module.css";

interface SelfcheckDto {
  status: JudgeCheckStatus;
  good_score: number | null;
  bad_score: number | null;
  gap: number | null;
  model: string;
  checked_at: string;
  error: string | null;
}

interface RubricDto {
  id: string;
  version: number;
  text: string;
}

type Gate = "passed" | "failed" | "none";

function gateTone(g: Gate | undefined): StatusTone {
  if (g === "passed") return "success";
  if (g === "failed") return "danger";
  return "neutral";
}

function judgeChipTone(s: JudgeCheckStatus | null): StatusTone {
  if (s === "calibrated") return "success";
  if (s === "uncalibrated") return "warning";
  return "neutral";
}

function deltaClass(d: number | null): string {
  const tone = deltaTone(d);
  if (tone === "success") return `${styles.delta} ${styles.deltaSuccess}`;
  if (tone === "danger") return `${styles.delta} ${styles.deltaDanger}`;
  return `${styles.delta} ${styles.deltaNeutral}`;
}

const NEW_FORM_ORDER = ["title", "aspect_key"] as const;

export default function FitnessSection() {
  const [status, setStatus] = useState<"loading" | "hidden" | "error" | "ready">("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [judgeConfigured, setJudgeConfigured] = useState(false);
  const [scorecards, setScorecards] = useState<ScorecardDto[]>([]);
  const [cases, setCases] = useState<EvalCaseDto[]>([]);
  const [selfcheck, setSelfcheck] = useState<SelfcheckDto | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const [runningAspect, setRunningAspect] = useState<string | null>(null);
  const [checkingJudge, setCheckingJudge] = useState(false);

  const [casesOpen, setCasesOpen] = useState(false);
  const [rubricsOpen, setRubricsOpen] = useState(false);
  const [rubrics, setRubrics] = useState<RubricDto[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [fTitle, setFTitle] = useState("");
  const [fAspect, setFAspect] = useState("agent_prompts/developer");
  const [fLevel, setFLevel] = useState<SignalLevel>("deterministic");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const refreshScorecards = useCallback(async () => {
    const sc = (await EvolutionFitness.scorecard()) as { scorecards?: ScorecardDto[] };
    setScorecards(sc.scorecards ?? []);
  }, []);

  const refreshCases = useCallback(async () => {
    const cs = await EvolutionFitness.cases({});
    const data = cs.data as { cases?: EvalCaseDto[] };
    setCases(data?.cases ?? []);
  }, []);

  const load = useCallback(async () => {
    try {
      const h = (await EvolutionFitness.health()) as { flag_enabled: boolean; judge_configured: boolean };
      if (!h.flag_enabled) {
        setStatus("hidden");
        return;
      }
      setJudgeConfigured(Boolean(h.judge_configured));
      setStatus("loading");
      const [sc, cs, last] = await Promise.all([
        EvolutionFitness.scorecard() as Promise<{ scorecards?: ScorecardDto[] }>,
        EvolutionFitness.cases({}),
        EvolutionFitness.judgeSelfcheckLast() as Promise<{ selfcheck: SelfcheckDto | null }>,
      ]);
      setScorecards(sc.scorecards ?? []);
      const cdata = cs.data as { cases?: EvalCaseDto[] };
      setCases(cdata?.cases ?? []);
      setSelfcheck(last.selfcheck ?? null);
      setStatus("ready");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runEvals = async (aspectKey: string) => {
    setRunningAspect(aspectKey);
    try {
      const res = await EvolutionFitness.run(aspectKey, true);
      if (res.status === 409) {
        setToast({ variant: "warning", body: "Ya hay una corrida en curso." });
      } else if (res.ok) {
        await refreshScorecards();
      } else {
        setToast({ variant: "error", body: "No se pudo correr la evaluación." });
      }
    } finally {
      setRunningAspect(null);
    }
  };

  const probarJuez = async () => {
    setCheckingJudge(true);
    try {
      const res = await EvolutionFitness.judgeSelfcheck();
      if (res.ok) {
        const data = res.data as { selfcheck: SelfcheckDto };
        setSelfcheck(data.selfcheck);
      } else if (res.status === 409) {
        setToast({ variant: "warning", body: "El juez local está deshabilitado." });
      } else {
        setToast({ variant: "error", body: "No se pudo probar el juez." });
      }
    } finally {
      setCheckingJudge(false);
    }
  };

  const toggleCase = async (c: EvalCaseDto) => {
    const res = await EvolutionFitness.patchCase(c.id, { enabled: !c.enabled });
    if (res.ok) {
      await refreshCases();
    } else {
      setToast({ variant: "error", body: "No se pudo actualizar el caso." });
    }
  };

  const toggleRubrics = async () => {
    if (!rubricsOpen && rubrics.length === 0) {
      const r = (await EvolutionFitness.rubrics()) as { rubrics?: RubricDto[] };
      setRubrics(r.rubrics ?? []);
    }
    setRubricsOpen((o) => !o);
  };

  const submitNew = async () => {
    const errors: Record<string, string> = {};
    if (!fTitle.trim()) errors.title = "El título es obligatorio.";
    if (!fAspect.trim()) errors.aspect_key = "El aspecto es obligatorio.";
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      const focusId = firstErrorFieldId("fit-new", NEW_FORM_ORDER, errors);
      if (focusId) document.getElementById(focusId)?.focus();
      return;
    }
    setFormErrors({});
    const body =
      fLevel === "llm_judge"
        ? {
            aspect_key: fAspect,
            subject: "artifact",
            level: "llm_judge",
            origin: "manual",
            title: fTitle,
            input: { kind: "artifact_text" },
            rubric_id: "prompt_de_agente",
          }
        : {
            aspect_key: fAspect,
            subject: "artifact",
            level: "deterministic",
            origin: "manual",
            title: fTitle,
            input: { kind: "artifact_text" },
            checks: [{ kind: "min_len", value: 1 }],
          };
    const res = await EvolutionFitness.createCase(body);
    if (res.ok) {
      setToast({ variant: "success", body: "Caso creado." });
      setFTitle("");
      setFormOpen(false);
      await refreshCases();
    } else {
      const data = res.data as { message?: string };
      setToast({ variant: "error", body: data?.message || "No se pudo crear el caso." });
    }
  };

  if (status === "hidden") return null;

  return (
    <div className={styles.section}>
      {toast ? <Toast toast={toast} onClose={() => setToast(null)} /> : null}

      <div className={styles.headerRow}>
        <SectionHeader
          title="Fitness de agentes"
          subtitle="Señal objetiva por aspecto: deterministas > ejecución > juez LLM."
        />
        <div className={styles.chipRow}>
          {!judgeConfigured ? (
            <StatusChip tone="neutral">Juez local sin configurar — solo señales deterministas</StatusChip>
          ) : null}
          <StatusChip tone={judgeChipTone(selfcheck?.status ?? null)}>
            {judgeCheckLabel(selfcheck?.status ?? null)}
          </StatusChip>
          <Button variant="secondary" size="sm" onClick={() => void probarJuez()} disabled={checkingJudge}>
            {checkingJudge ? <Spinner /> : "Probar juez"}
          </Button>
        </div>
      </div>

      {status === "loading" ? (
        <SkeletonList rows={4} ariaLabel="Cargando fitness" />
      ) : status === "error" ? (
        <Card>
          <div className={styles.errorBanner}>
            <span>No se pudo cargar el fitness: {errorMsg}</span>
            <Button variant="secondary" size="sm" onClick={() => void load()}>
              Reintentar
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div className={styles.grid}>
            {scorecards.map((sc) => (
              <Card key={sc.aspect_key}>
                <div className={styles.card}>
                  <div className={styles.aspectName}>{aspectLabel(sc.aspect_key)}</div>
                  <div className={styles.scoreBig}>{scoreDisplay(sc.latest?.score ?? null)}</div>
                  <div className={styles.metaRow}>
                    <StatusChip tone={gateTone(sc.latest?.deterministic_gate)}>
                      {gateLabel(sc.latest?.deterministic_gate ?? "none")}
                    </StatusChip>
                    <span className={deltaClass(sc.delta)}>{deltaDisplay(sc.delta)}</span>
                    <span>
                      casos: {sc.cases_enabled}/{sc.cases_total}
                    </span>
                  </div>
                  {sc.history.length > 0 ? (
                    <div className={styles.historyText}>
                      {sc.history.map((h) => scoreDisplay(h.score)).join(" · ")}
                    </div>
                  ) : null}
                  <div className={styles.actions}>
                    <Button
                      size="sm"
                      onClick={() => void runEvals(sc.aspect_key)}
                      disabled={runningAspect === sc.aspect_key}
                    >
                      {runningAspect === sc.aspect_key ? <Spinner /> : "Correr evals"}
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
            {scorecards.length === 0 ? (
              <p className={styles.muted}>Todavía no hay corridas. Corré una evaluación desde un aspecto.</p>
            ) : null}
          </div>

          <div className={styles.collapsible}>
            <div className={styles.collapsibleHead}>
              <strong>Casos de evaluación ({cases.length})</strong>
              <Button variant="ghost" size="sm" onClick={() => setCasesOpen((o) => !o)}>
                {casesOpen ? "Ocultar" : "Ver casos"}
              </Button>
            </div>
            {casesOpen ? (
              <>
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Título</th>
                        <th>Aspecto</th>
                        <th>Nivel</th>
                        <th>Origen</th>
                        <th>Peso</th>
                        <th>Estado</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {cases.map((c) => {
                        const isDraft = !c.enabled && (c.origin === "incident" || c.origin === "execution");
                        return (
                          <tr key={c.id} className={isDraft ? styles.draftRow : undefined}>
                            <td>
                              {c.title}{" "}
                              {isDraft ? <StatusChip tone="warning">Borrador — revisá y habilitá</StatusChip> : null}
                            </td>
                            <td>{aspectLabel(c.aspect_key)}</td>
                            <td>
                              <StatusChip tone={levelTone(c.level)}>{levelLabel(c.level)}</StatusChip>
                            </td>
                            <td>{c.origin}</td>
                            <td>{c.weight}</td>
                            <td>{c.enabled ? "Habilitado" : "Deshabilitado"}</td>
                            <td>
                              {c.enabled ? (
                                <ConfirmButton label="Deshabilitar" onConfirm={() => void toggleCase(c)} />
                              ) : (
                                <Button size="sm" onClick={() => void toggleCase(c)}>
                                  Habilitar
                                </Button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className={styles.formActions}>
                  <Button variant="secondary" size="sm" onClick={() => setFormOpen((o) => !o)}>
                    {formOpen ? "Cancelar" : "Nuevo caso"}
                  </Button>
                </div>
                {formOpen ? (
                  <>
                    <div className={styles.formGrid}>
                      <Field label="Título" id="fit-new-title" error={formErrors.title}>
                        {(ctl) => (
                          <Input
                            {...ctl}
                            value={fTitle}
                            invalid={Boolean(formErrors.title)}
                            onChange={(e) => setFTitle(e.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Aspecto (aspect_key)" id="fit-new-aspect_key" error={formErrors.aspect_key}>
                        {(ctl) => (
                          <Input
                            {...ctl}
                            value={fAspect}
                            invalid={Boolean(formErrors.aspect_key)}
                            onChange={(e) => setFAspect(e.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Nivel" id="fit-new-level">
                        {(ctl) => (
                          <Select
                            {...ctl}
                            value={fLevel}
                            onChange={(e) => setFLevel(e.target.value as SignalLevel)}
                          >
                            <option value="deterministic">Determinista</option>
                            <option value="llm_judge">Juez LLM</option>
                          </Select>
                        )}
                      </Field>
                    </div>
                    <div className={styles.formActions}>
                      <Button size="sm" onClick={() => void submitNew()}>
                        Crear caso
                      </Button>
                    </div>
                  </>
                ) : null}
              </>
            ) : null}
          </div>

          <div className={styles.collapsible}>
            <div className={styles.collapsibleHead}>
              <strong>Rúbricas del juez</strong>
              <Button variant="ghost" size="sm" onClick={() => void toggleRubrics()}>
                {rubricsOpen ? "Ocultar" : "Ver rúbricas"}
              </Button>
            </div>
            {rubricsOpen ? (
              <div className={styles.rubricList}>
                {rubrics.map((r) => (
                  <div key={r.id}>
                    <div className={styles.aspectName}>
                      {r.id} v{r.version}
                    </div>
                    <pre className={styles.pre}>{r.text}</pre>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

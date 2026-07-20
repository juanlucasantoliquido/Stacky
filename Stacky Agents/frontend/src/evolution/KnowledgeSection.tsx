// Plan 170 F6 — sección "Conocimiento (flywheel)" del Centro de Evolución.
// TODO estilo va en el .module.css (G6: cero style inline). CERO pollers (G9):
// carga on-mount + botones + refresh post-acción. Con la flag OFF no renderiza nada.
import { useCallback, useEffect, useState } from "react";
import { EvolutionKnowledge, Evolution } from "../api/endpoints";
import { Button, Card, SectionHeader, StatusChip, Field, Input, Textarea, Select } from "../components/ui";
import { firstErrorFieldId } from "../components/ui";
import ConfirmButton from "../components/ConfirmButton";
import SkeletonList from "../components/SkeletonList";
import Toast, { type ToastState } from "../components/Toast";
import { formatDateTime, formatInt } from "../services/format";
import {
  type LessonDto,
  type HarvestCandidatesDto,
  type KnowledgeOverviewDto,
  type InjectionPreviewDto,
  scopeLabel,
  lessonStatusChip,
  formatDelta,
  validateManualLesson,
  sortCandidates,
} from "./knowledgeModel";
import styles from "./KnowledgeSection.module.css";

type Tab = "lessons" | "harvest" | "new";
const RETIRE_NOTE = "retiro de lección desde el panel de conocimiento";
const MANUAL_ORDER = ["title", "body"] as const;

export default function KnowledgeSection() {
  const [status, setStatus] = useState<"loading" | "hidden" | "error" | "ready">("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("lessons");
  const [toast, setToast] = useState<ToastState | null>(null);

  const [overview, setOverview] = useState<KnowledgeOverviewDto | null>(null);
  const [lessons, setLessons] = useState<LessonDto[]>([]);
  const [candidates, setCandidates] = useState<HarvestCandidatesDto | null>(null);

  const [previewAgent, setPreviewAgent] = useState<string>("");
  const [previewQuery, setPreviewQuery] = useState<string>("");
  const [preview, setPreview] = useState<InjectionPreviewDto | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const [mTitle, setMTitle] = useState("");
  const [mBody, setMBody] = useState("");
  const [mErrors, setMErrors] = useState<Record<string, string>>({});

  const [dupPrompt, setDupPrompt] = useState<{ kind: "incident" | "optimizer"; id: string } | null>(null);

  const refreshLessons = useCallback(async () => {
    const r = await EvolutionKnowledge.lessons(true);
    const d = r.data as { lessons?: LessonDto[] };
    setLessons(d?.lessons ?? []);
  }, []);

  const refreshOverview = useCallback(async () => {
    const r = await EvolutionKnowledge.overview();
    setOverview(r.data as KnowledgeOverviewDto);
  }, []);

  const refreshCandidates = useCallback(async () => {
    const r = await EvolutionKnowledge.candidates();
    setCandidates(r.data as HarvestCandidatesDto);
  }, []);

  const load = useCallback(async () => {
    try {
      const h = (await EvolutionKnowledge.health()) as { flag_enabled: boolean };
      if (!h.flag_enabled) {
        setStatus("hidden");
        return;
      }
      setStatus("loading");
      await Promise.all([refreshOverview(), refreshLessons(), refreshCandidates()]);
      setStatus("ready");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, [refreshOverview, refreshLessons, refreshCandidates]);

  useEffect(() => {
    void load();
  }, [load]);

  const notify = (variant: ToastState["variant"], body: string) => setToast({ variant, body });

  const retire = async (lessonId: string) => {
    const r = await Evolution.transition(lessonId, "rollback", RETIRE_NOTE);
    if (r.ok) {
      notify("success", "Lección retirada.");
      await Promise.all([refreshLessons(), refreshOverview()]);
    } else {
      notify("error", "No se pudo retirar la lección.");
    }
  };

  const protectWithCase = async (lessonId: string) => {
    const r = await EvolutionKnowledge.toEvalCase(lessonId);
    if (r.ok) {
      notify("success", "Caso de eval borrador creado. Completá el check en Fitness.");
      await Promise.all([refreshLessons(), refreshOverview()]);
    } else {
      const err = (r.data as { error?: string })?.error ?? "error";
      notify("warning", `No se creó el caso (${err}).`);
    }
  };

  const harvestIncident = async (incidentId: string, force = false) => {
    const r = await EvolutionKnowledge.fromIncident(incidentId, force);
    if (r.ok) {
      notify("success", "Lección propuesta desde la incidencia. Aprobala en Propuestas.");
      setDupPrompt(null);
      await Promise.all([refreshCandidates(), refreshOverview()]);
    } else if (r.status === 409 && (r.data as { error?: string })?.error === "duplicate_suspect") {
      setDupPrompt({ kind: "incident", id: incidentId });
      notify("warning", "Ya existe una lección muy similar. Confirmá abajo para crear igual.");
    } else {
      notify("error", "No se pudo cosechar la incidencia.");
    }
  };

  const promoteOptimizer = async (lessonId: string, force = false) => {
    const r = await EvolutionKnowledge.fromOptimizerLesson(lessonId, force);
    if (r.ok) {
      notify("success", "Mejora promovida a lección. Aprobala en Propuestas.");
      setDupPrompt(null);
      await Promise.all([refreshCandidates(), refreshOverview()]);
    } else if (r.status === 409 && (r.data as { error?: string })?.error === "duplicate_suspect") {
      setDupPrompt({ kind: "optimizer", id: lessonId });
      notify("warning", "Ya existe una lección muy similar. Confirmá abajo para crear igual.");
    } else {
      notify("error", "No se pudo promover la mejora.");
    }
  };

  const confirmDup = async () => {
    if (!dupPrompt) return;
    if (dupPrompt.kind === "incident") await harvestIncident(dupPrompt.id, true);
    else await promoteOptimizer(dupPrompt.id, true);
  };

  const submitManual = async () => {
    const v = validateManualLesson({ title: mTitle, body: mBody });
    setMErrors(v.errors);
    if (!v.ok) {
      const fid = firstErrorFieldId("kmanual", MANUAL_ORDER, v.errors);
      if (fid) document.getElementById(fid)?.focus();
      return;
    }
    const r = await EvolutionKnowledge.manual(mTitle, mBody);
    if (r.ok) {
      notify("success", "Lección propuesta. Aprobala en Propuestas.");
      setMTitle("");
      setMBody("");
      await refreshOverview();
      setTab("lessons");
    } else if (r.status === 409) {
      notify("warning", "Ya existe una lección muy similar.");
    } else {
      notify("error", "No se pudo crear la lección.");
    }
  };

  const runPreview = async () => {
    const r = await EvolutionKnowledge.injectionPreview({
      agent_type: previewAgent || undefined,
      query: previewQuery || undefined,
    });
    setPreview(r.data as InjectionPreviewDto);
  };

  if (status === "hidden") return null;
  if (status === "loading") {
    return (
      <section className={styles.section}>
        <SkeletonList rows={5} />
      </section>
    );
  }
  if (status === "error") {
    return (
      <section className={styles.section}>
        <Card padding="md">Error cargando el flywheel: {errorMsg}</Card>
      </section>
    );
  }

  const activeLessons = lessons.filter((l) => l.active);
  const agentOptions = overview ? Object.keys(overview.coverage.by_agent_type) : [];

  return (
    <section className={styles.section}>
      <div className={styles.headerRow}>
        <SectionHeader title="Conocimiento (flywheel)" />
        <Button variant="secondary" size="sm" onClick={() => void load()}>
          Refrescar
        </Button>
      </div>

      {overview && (
        <div className={styles.grid}>
          <Card padding="sm">
            <div className={styles.kpiLabel}>Lecciones activas</div>
            <div className={styles.kpiValue}>{formatInt(overview.lessons.active)}</div>
          </Card>
          <Card padding="sm">
            <div className={styles.kpiLabel}>Cobertura de agentes</div>
            <div className={styles.kpiValue}>
              {overview.coverage.agents_with_lessons}/{overview.coverage.agents_total}
            </div>
          </Card>
          <Card padding="sm">
            <div className={styles.kpiLabel}>Casos de eval de incidencias</div>
            <div className={styles.kpiValue}>{formatInt(overview.flywheel.eval_cases_from_incidents)}</div>
          </Card>
          <Card padding="sm">
            <div className={styles.kpiLabel}>Δ fitness lecciones</div>
            <div className={styles.kpiValue}>{formatDelta(overview.fitness_knowledge.delta)}</div>
            <div className={styles.kpiHint}>correlación, no causalidad</div>
          </Card>
        </div>
      )}

      {overview && overview.retire_suggestions.length > 0 && (
        <Card padding="sm" className={styles.suggestBanner}>
          <strong>Sugerencias de retiro</strong>
          <ul className={styles.suggestList}>
            {overview.retire_suggestions.map((s) => (
              <li key={s.lesson_id}>
                {s.title} — {s.reason === "lru_por_uso" ? "poco usada" : "sin uso prolongado"}
              </li>
            ))}
          </ul>
          <span className={styles.kpiHint}>Solo sugerencia: retirar lo decidís vos.</span>
        </Card>
      )}

      <div className={styles.tabsRow}>
        <button
          className={tab === "lessons" ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab("lessons")}
        >
          Lecciones
        </button>
        <button
          className={tab === "harvest" ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab("harvest")}
        >
          Cosechar
        </button>
        <button
          className={tab === "new" ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab("new")}
        >
          Nueva lección
        </button>
      </div>

      {tab === "lessons" && (
        <div className={styles.list}>
          <div className={styles.previewBox}>
            <button className={styles.collapseBtn} onClick={() => setPreviewOpen((o) => !o)}>
              {previewOpen ? "▾" : "▸"} Vista previa de inyección
            </button>
            {previewOpen && (
              <div className={styles.previewBody}>
                <div className={styles.previewControls}>
                  <Select
                    value={previewAgent}
                    onChange={(e) => setPreviewAgent(e.target.value)}
                    aria-label="Agente"
                  >
                    <option value="">— cualquier agente —</option>
                    {agentOptions.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </Select>
                  <Input
                    value={previewQuery}
                    onChange={(e) => setPreviewQuery(e.target.value)}
                    placeholder="query opcional (título del ticket)"
                    aria-label="Query"
                  />
                  <Button variant="secondary" size="sm" onClick={() => void runPreview()}>
                    Previsualizar
                  </Button>
                </div>
                {preview &&
                  (preview.block ? (
                    <>
                      <div className={styles.kpiHint}>
                        {preview.matched_count} lecciones matchean; esto es EXACTAMENTE lo que
                        recibiría el agente.
                      </div>
                      <pre className={styles.previewPre}>{preview.block.content}</pre>
                    </>
                  ) : (
                    <div className={styles.kpiHint}>Ninguna lección matchea ese scope.</div>
                  ))}
              </div>
            )}
          </div>

          {activeLessons.length === 0 ? (
            <Card padding="md">
              Todavía no hay lecciones. Cosechá la primera desde una incidencia resuelta.
            </Card>
          ) : (
            lessons.map((l) => {
              const chip = lessonStatusChip(l);
              return (
                <Card key={l.lesson_id} padding="sm">
                  <div className={styles.lessonRow}>
                    <div className={styles.lessonMain}>
                      <div className={styles.lessonTitle}>{l.title}</div>
                      <div className={styles.lessonMeta}>
                        <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
                        <span>{scopeLabel(l.scope)}</span>
                        <span>Seleccionada {formatInt(l.usage_count)}x</span>
                        <span>{formatDateTime(l.last_injected_at)}</span>
                        <a href={`?proposal=${l.lesson_id}`}>origen</a>
                      </div>
                    </div>
                    {l.active && (
                      <div className={styles.lessonActions}>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={Boolean(l.eval_case_id)}
                          onClick={() => void protectWithCase(l.lesson_id)}
                        >
                          {l.eval_case_id ? "Protegida" : "Proteger con caso"}
                        </Button>
                        <ConfirmButton label="Retirar" onConfirm={() => void retire(l.lesson_id)} />
                      </div>
                    )}
                  </div>
                </Card>
              );
            })
          )}
        </div>
      )}

      {tab === "harvest" && (
        <div className={styles.list}>
          {dupPrompt && (
            <Card padding="sm" className={styles.suggestBanner}>
              <span>Ya existe una lección muy similar. ¿Crear igual de todas formas?</span>
              <div className={styles.lessonActions}>
                <Button variant="primary" size="sm" onClick={() => void confirmDup()}>
                  Crear igual
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setDupPrompt(null)}>
                  Cancelar
                </Button>
              </div>
            </Card>
          )}
          <div className={styles.kpiLabel}>Incidencias publicadas</div>
          {!candidates || candidates.incidents.length === 0 ? (
            <Card padding="md">No hay incidencias publicadas para cosechar.</Card>
          ) : (
            sortCandidates(candidates.incidents).map((i) => (
              <Card key={i.incident_id} padding="sm">
                <div className={styles.lessonRow}>
                  <div className={styles.lessonMain}>
                    <div className={styles.lessonTitle}>{i.title}</div>
                    <div className={styles.lessonMeta}>
                      {i.has_dev_run && <StatusChip tone="success">con resolución verificada</StatusChip>}
                      <span>{formatDateTime(i.created_at)}</span>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={i.already_harvested}
                    onClick={() => void harvestIncident(i.incident_id)}
                  >
                    {i.already_harvested ? "Ya cosechada" : "Extraer lección"}
                  </Button>
                </div>
              </Card>
            ))
          )}

          <div className={styles.kpiLabel}>Mejoras verificadas del optimizador</div>
          {!candidates || candidates.optimizer_lessons.length === 0 ? (
            <Card padding="md">No hay mejoras verificadas para promover.</Card>
          ) : (
            candidates.optimizer_lessons.map((o) => (
              <Card key={o.lesson_id} padding="sm">
                <div className={styles.lessonRow}>
                  <div className={styles.lessonMain}>
                    <div className={styles.lessonTitle}>{o.aspect_key}</div>
                    <div className={styles.lessonMeta}>
                      <span>Δ {formatDelta(o.delta)}</span>
                      <span>{o.text}</span>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={o.already_harvested}
                    onClick={() => void promoteOptimizer(o.lesson_id)}
                  >
                    {o.already_harvested ? "Ya cosechada" : "Promover a lección"}
                  </Button>
                </div>
              </Card>
            ))
          )}
        </div>
      )}

      {tab === "new" && (
        <Card padding="md">
          <div className={styles.form}>
            <Field label="Título" required error={mErrors.title} id="kmanual-title">
              {(ctl) => (
                <Input
                  {...ctl}
                  value={mTitle}
                  invalid={Boolean(mErrors.title)}
                  maxLength={80}
                  onChange={(e) => setMTitle(e.target.value)}
                />
              )}
            </Field>
            <Field label="Cuerpo (qué pasó, causa raíz, regla accionable)" required error={mErrors.body} id="kmanual-body">
              {(ctl) => (
                <Textarea
                  {...ctl}
                  value={mBody}
                  invalid={Boolean(mErrors.body)}
                  rows={5}
                  maxLength={1200}
                  onChange={(e) => setMBody(e.target.value)}
                />
              )}
            </Field>
            <div>
              <Button variant="primary" onClick={() => void submitManual()}>
                Proponer lección
              </Button>
            </div>
          </div>
        </Card>
      )}

      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </section>
  );
}

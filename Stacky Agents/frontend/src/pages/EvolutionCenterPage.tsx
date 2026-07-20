// Plan 167 F6 — Centro de Evolución. TODO estilo va en el .module.css (G6: cero
// estilos inline en este archivo). CERO pollers (G9): carga on-mount + botón
// Refrescar + refresh tras cada acción exitosa. Deep-link ?proposal= (G10).
import { useCallback, useEffect, useMemo, useState } from "react";
import { Evolution, EvolutionFitness } from "../api/endpoints";
import {
  Button,
  Card,
  SectionHeader,
  StatusChip,
  Field,
  Input,
  Select,
  Textarea,
  Checkbox,
  firstErrorFieldId,
} from "../components/ui";
import ConfirmButton from "../components/ConfirmButton";
import EmptyState from "../components/EmptyState";
import SkeletonList from "../components/SkeletonList";
import Toast, { type ToastState } from "../components/Toast";
import { readQueryParam } from "../utils/queryParams";
import { formatDateTime, formatTokens } from "../services/format";
import {
  type AspectDto,
  type ProposalDto,
  type CycleDto,
  type OverviewDto,
  type ProposalFilters,
  type ProposalStatus,
  type ProposalOrigin,
  type ArtifactType,
  statusTone,
  statusLabel,
  loopModeLabel,
  filterProposals,
  availableActions,
  flagDeepLink,
  fitnessDisplay,
} from "../evolution/model";
import FitnessSection from "../evolution/FitnessSection";
import OptimizerSection from "../evolution/OptimizerSection";
import KnowledgeSection from "../evolution/KnowledgeSection";
import { canEvaluateProposal } from "../evolution/fitnessModel";
import styles from "./EvolutionCenterPage.module.css";

interface LedgerEvent {
  ts: string;
  event: string;
  proposal_id: string | null;
  action: string | null;
  from: string | null;
  to: string | null;
  actor: string | null;
  note: string | null;
  cycle_id: string | null;
}

const STATUS_OPTIONS: ProposalStatus[] = [
  "draft", "pending_review", "approved", "applied", "rejected", "rolled_back",
];
const ORIGIN_OPTIONS: ProposalOrigin[] = ["manual", "agent", "optimizer", "mape"];
const ARTIFACT_OPTIONS: ArtifactType[] = ["free_text", "knowledge_note", "prompt_file", "flag_change"];
const NEW_FORM_ORDER = ["title", "rationale"] as const;

export default function EvolutionCenterPage() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewDto | null>(null);
  const [proposals, setProposals] = useState<ProposalDto[]>([]);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [forceRollbackId, setForceRollbackId] = useState<string | null>(null);

  const [filters, setFilters] = useState<ProposalFilters>({
    status: "TODAS", aspectId: "TODOS", origin: "TODOS",
  });

  const [cycleRunning, setCycleRunning] = useState(false);
  const [cycleSummary, setCycleSummary] = useState<CycleDto | null>(null);
  const [useLlm, setUseLlm] = useState(true);
  const [showCycleButton, setShowCycleButton] = useState(true);

  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [ledgerEvents, setLedgerEvents] = useState<LedgerEvent[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formAspect, setFormAspect] = useState("agent_prompts");
  const [formArtifact, setFormArtifact] = useState<ArtifactType>("free_text");
  const [formRationale, setFormRationale] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formTargetRef, setFormTargetRef] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [ov, pr] = await Promise.all([Evolution.overview(), Evolution.proposals()]);
      setOverview(ov as OverviewDto);
      setProposals(((pr as { proposals?: ProposalDto[] }).proposals) ?? []);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const pid = readQueryParam("proposal");
    if (pid) setExpandedId(pid);
  }, [load]);

  const filtered = useMemo(() => filterProposals(proposals, filters), [proposals, filters]);

  const aspects: AspectDto[] = overview?.aspects ?? [];

  const doAction = async (p: ProposalDto, action: string, force?: boolean) => {
    const res = await Evolution.transition(p.id, action, undefined, force);
    if (res.ok) {
      setForceRollbackId(null);
      setToast({ variant: "success", body: `Acción "${action}" aplicada a la propuesta.` });
      await load();
      return;
    }
    const err = (res.data as { error?: string; message?: string }) || {};
    if (err.error === "target_drifted" && action === "apply") {
      setToast({
        variant: "warning",
        body: "El artefacto cambió desde que se creó la propuesta — regenerala.",
      });
    } else if (err.error === "target_drifted" && action === "rollback") {
      setForceRollbackId(p.id);
      setToast({
        variant: "warning",
        body: "El artefacto fue editado tras aplicarse. Podés forzar el revert para pisar la edición manual.",
      });
    } else {
      setToast({ variant: "error", body: err.message || `No se pudo aplicar (${res.status}).` });
    }
  };

  const runCycle = async () => {
    setCycleRunning(true);
    setCycleSummary(null);
    try {
      const res = await Evolution.runCycle(useLlm);
      const data = res.data as { error?: string; message?: string; cycle?: CycleDto };
      if (res.ok && data.cycle) {
        setCycleSummary(data.cycle);
        await load();
      } else if (res.status === 409) {
        setToast({ variant: "warning", body: "Ya hay un ciclo corriendo." });
      } else if (res.status === 404 && data.error === "evolution_cycle_disabled") {
        setShowCycleButton(false);
      } else {
        setToast({ variant: "error", body: data.message || "No se pudo correr el ciclo." });
      }
    } finally {
      setCycleRunning(false);
    }
  };

  const evaluateFitness = async (p: ProposalDto) => {
    const res = await EvolutionFitness.proposalFitnessRun(p.id, "both", true);
    if (res.ok) {
      setToast({ variant: "success", body: "Fitness before/after evaluado (sin aplicar nada)." });
      await load();
    } else {
      const err = (res.data as { error?: string; message?: string }) || {};
      if (err.error === "fitness_not_applicable") {
        setToast({ variant: "warning", body: "Esta propuesta no es evaluable por fitness." });
      } else {
        setToast({ variant: "error", body: err.message || `No se pudo evaluar (${res.status}).` });
      }
    }
  };

  const toggleLedger = async () => {
    if (!ledgerOpen) {
      try {
        const d = await Evolution.ledger(50);
        setLedgerEvents(((d as { events?: LedgerEvent[] }).events) ?? []);
      } catch {
        setLedgerEvents([]);
      }
    }
    setLedgerOpen((o) => !o);
  };

  const submitNew = async () => {
    const errors: Record<string, string> = {};
    if (!formTitle.trim()) errors.title = "El título es obligatorio.";
    if (!formRationale.trim()) errors.rationale = "El racional es obligatorio.";
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      const focusId = firstErrorFieldId("evo-new", NEW_FORM_ORDER, errors);
      if (focusId) document.getElementById(focusId)?.focus();
      return;
    }
    setFormErrors({});
    const res = await Evolution.createProposal({
      aspect_id: formAspect,
      title: formTitle,
      rationale: formRationale,
      artifact_type: formArtifact,
      proposed_content: formContent || null,
      target_ref: formTargetRef || null,
      origin: "manual",
      initial_status: "pending_review",
    });
    if (res.ok) {
      setToast({ variant: "success", body: "Propuesta creada." });
      setFormOpen(false);
      setFormTitle("");
      setFormRationale("");
      setFormContent("");
      setFormTargetRef("");
      await load();
    } else {
      const data = res.data as { message?: string };
      setToast({ variant: "error", body: data.message || "No se pudo crear la propuesta." });
    }
  };

  const showTargetRef = formArtifact === "prompt_file" || formArtifact === "flag_change";
  const counts = overview?.counts;
  const lastCycle = overview?.last_cycle ?? null;

  return (
    <div className={styles.page}>
      {toast ? <Toast toast={toast} onClose={() => setToast(null)} /> : null}

      <div className={styles.header}>
        <div>
          <h2 className={styles.pageTitle}>🧬 Centro de Evolución</h2>
          <p className={styles.pageSubtitle}>
            Registro, gobierno y auditoría de las mejoras del propio Stacky. Nada se aplica sin tu aprobación.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void load()}>↻ Refrescar</Button>
      </div>

      {loading ? (
        <SkeletonList rows={6} ariaLabel="Cargando Centro de Evolución" />
      ) : loadError ? (
        <Card>
          <div className={styles.errorBanner}>
            <span>No se pudo cargar el Centro de Evolución: {loadError}</span>
            <Button variant="secondary" size="sm" onClick={() => void load()}>Reintentar</Button>
          </div>
        </Card>
      ) : (
        <>
          {/* Hero de KPIs */}
          <div className={styles.heroRow}>
            <Card><div className={styles.kpi}><span className={styles.kpiN}>{counts?.pending_review ?? 0}</span><span className={styles.kpiL}>Propuestas en revisión</span></div></Card>
            <Card><div className={styles.kpi}><span className={styles.kpiN}>{counts?.applied ?? 0}</span><span className={styles.kpiL}>Aplicadas</span></div></Card>
            <Card><div className={styles.kpi}><span className={styles.kpiN}>{aspects.length}</span><span className={styles.kpiL}>Aspectos</span></div></Card>
            <Card>
              <div className={styles.kpi}>
                <span className={styles.kpiL}>
                  {lastCycle
                    ? `Último ciclo: ${formatDateTime(lastCycle.finished_at)} · ${formatTokens(lastCycle.tokens_est_in + lastCycle.tokens_est_out)} tokens est.`
                    : "— todavía sin ciclos"}
                </span>
              </div>
            </Card>
          </div>

          {/* Ciclo MAPE */}
          {showCycleButton ? (
            <Card>
              <div className={styles.cycleBar}>
                <div className={styles.cycleControls}>
                  <Button variant="primary" size="md" loading={cycleRunning} onClick={() => void runCycle()}>
                    Correr ciclo MAPE
                  </Button>
                  <Checkbox
                    label="Usar modelo local si está configurado"
                    checked={useLlm}
                    onChange={(e) => setUseLlm(e.target.checked)}
                  />
                </div>
                {cycleSummary ? (
                  <div className={styles.cycleSummary}>
                    <span>Reglas: {cycleSummary.rules_fired.join(", ") || "ninguna"}</span>
                    <span>Propuestas creadas: {cycleSummary.proposal_ids.length}</span>
                    <span>LLM: {cycleSummary.llm_used ? "usado" : "no usado"}</span>
                    <span>Tokens est.: {formatTokens(cycleSummary.tokens_est_in + cycleSummary.tokens_est_out)}</span>
                    {cycleSummary.signals_truncated ? (
                      <span className={styles.warnText}>señales truncadas por presupuesto</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </Card>
          ) : null}

          {/* Aspectos */}
          <SectionHeader title="Aspectos mejorables" subtitle="Las áreas de Stacky que este panel gobierna." />
          <div className={styles.aspectGrid}>
            {aspects.map((a) => (
              <Card key={a.id}>
                <div className={styles.aspectCard}>
                  <div className={styles.aspectHead}>
                    <strong>{a.name}</strong>
                    <StatusChip tone={a.loop_mode === "human_on_the_loop" ? "warning" : "info"}>
                      {loopModeLabel(a.loop_mode)}
                    </StatusChip>
                  </div>
                  <p className={styles.aspectDesc}>{a.description}</p>
                  {a.id === "knowledge_rag" ? (
                    <p className={styles.aspectHint}>auto-aplicación configurable en el Arnés</p>
                  ) : null}
                  <div className={styles.aspectLinks}>
                    {a.links.map((l) => (
                      <a key={l.href} className={styles.aspectLink} href={l.href}>{l.label}</a>
                    ))}
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Propuestas */}
          <SectionHeader
            title="Propuestas"
            actions={
              <Button variant="secondary" size="sm" onClick={() => setFormOpen((o) => !o)}>
                {formOpen ? "Cerrar" : "Nueva propuesta"}
              </Button>
            }
          />

          {formOpen ? (
            <Card>
              <div className={styles.form}>
                <Field label="Título" required id="evo-new-title" error={formErrors.title}>
                  {(ctl) => (
                    <Input {...ctl} value={formTitle} onChange={(e) => setFormTitle(e.target.value)}
                      invalid={!!formErrors.title} />
                  )}
                </Field>
                <Field label="Aspecto" id="evo-new-aspect">
                  {(ctl) => (
                    <Select {...ctl} value={formAspect} onChange={(e) => setFormAspect(e.target.value)}>
                      {aspects.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Tipo de artefacto" id="evo-new-artifact">
                  {(ctl) => (
                    <Select {...ctl} value={formArtifact}
                      onChange={(e) => setFormArtifact(e.target.value as ArtifactType)}>
                      {ARTIFACT_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Racional" required id="evo-new-rationale" error={formErrors.rationale}>
                  {(ctl) => (
                    <Textarea {...ctl} value={formRationale}
                      onChange={(e) => setFormRationale(e.target.value)} invalid={!!formErrors.rationale} />
                  )}
                </Field>
                <Field label="Contenido propuesto" id="evo-new-content">
                  {(ctl) => (
                    <Textarea {...ctl} value={formContent} onChange={(e) => setFormContent(e.target.value)} />
                  )}
                </Field>
                {showTargetRef ? (
                  <Field label="Target ref (archivo o key de flag)" id="evo-new-targetref">
                    {(ctl) => (
                      <Input {...ctl} value={formTargetRef} onChange={(e) => setFormTargetRef(e.target.value)} />
                    )}
                  </Field>
                ) : null}
                <div className={styles.formActions}>
                  <Button variant="primary" size="md" onClick={() => void submitNew()}>Crear propuesta</Button>
                </div>
              </div>
            </Card>
          ) : null}

          <div className={styles.filters}>
            <Field label="Estado" id="evo-f-status">
              {(ctl) => (
                <Select {...ctl} value={filters.status}
                  onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as ProposalStatus | "TODAS" }))}>
                  <option value="TODAS">Todas</option>
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Aspecto" id="evo-f-aspect">
              {(ctl) => (
                <Select {...ctl} value={filters.aspectId}
                  onChange={(e) => setFilters((f) => ({ ...f, aspectId: e.target.value }))}>
                  <option value="TODOS">Todos</option>
                  {aspects.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Origen" id="evo-f-origin">
              {(ctl) => (
                <Select {...ctl} value={filters.origin}
                  onChange={(e) => setFilters((f) => ({ ...f, origin: e.target.value as ProposalOrigin | "TODOS" }))}>
                  <option value="TODOS">Todos</option>
                  {ORIGIN_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                </Select>
              )}
            </Field>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              variant="generic"
              title="Sin propuestas todavía"
              message="Corré un ciclo MAPE o creá una propuesta manual."
            />
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Título</th>
                    <th>Aspecto</th>
                    <th>Estado</th>
                    <th>Fitness</th>
                    <th>Actualizada</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => (
                    <ProposalRow
                      key={p.id}
                      p={p}
                      expanded={expandedId === p.id}
                      onToggle={() => setExpandedId((id) => (id === p.id ? null : p.id))}
                      onAction={doAction}
                      forceRollback={forceRollbackId === p.id}
                      onEvaluateFitness={evaluateFitness}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Ledger */}
          <SectionHeader
            title="Ledger de evolución"
            actions={
              <Button variant="ghost" size="sm" onClick={() => void toggleLedger()}>
                {ledgerOpen ? "Ocultar" : "Ver ledger"}
              </Button>
            }
          />
          {ledgerOpen ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr><th>Cuándo</th><th>Evento</th><th>Acción</th><th>Propuesta</th><th>Actor</th><th>Nota</th></tr>
                </thead>
                <tbody>
                  {ledgerEvents.map((e, i) => (
                    <tr key={i}>
                      <td>{formatDateTime(e.ts)}</td>
                      <td>{e.event}</td>
                      <td>{e.action ?? "—"}</td>
                      <td>{e.proposal_id ?? "—"}</td>
                      <td>{e.actor ?? "—"}</td>
                      <td>{e.note ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {/* Plan 168 — sección Fitness (no renderiza con la flag del arnés OFF) */}
          <FitnessSection />

          {/* Plan 169 — sección Optimizador (no renderiza con la flag del optimizador OFF) */}
          <OptimizerSection />

          {/* Plan 170 — sección Conocimiento (no renderiza con la flag del flywheel OFF) */}
          <KnowledgeSection />
        </>
      )}
    </div>
  );
}

function ProposalRow({
  p, expanded, onToggle, onAction, forceRollback, onEvaluateFitness,
}: {
  p: ProposalDto;
  expanded: boolean;
  onToggle: () => void;
  onAction: (p: ProposalDto, action: string, force?: boolean) => void;
  forceRollback: boolean;
  onEvaluateFitness: (p: ProposalDto) => void;
}) {
  const actions = availableActions(p);
  return (
    <>
      <tr className={styles.row} onClick={onToggle}>
        <td>
          <div className={styles.cellTitle}>{p.title}</div>
          <div className={styles.cellSub}>{p.origin}{p.evidence[0] ? ` · ${p.evidence[0]}` : ""}</div>
        </td>
        <td>{p.aspect_id}</td>
        <td><StatusChip tone={statusTone(p.status)}>{statusLabel(p.status)}</StatusChip></td>
        <td>{fitnessDisplay(p.fitness_before)}</td>
        <td>{formatDateTime(p.updated_at)}</td>
        <td onClick={(e) => e.stopPropagation()}>
          <div className={styles.actions}>
            {p.status === "approved" && p.artifact_type === "flag_change" && p.target_ref ? (
              <a className={styles.flagLink} href={flagDeepLink(p.target_ref) ?? "#"}>Cambiar en el Arnés</a>
            ) : null}
            {actions.map((a) =>
              a.confirm ? (
                <ConfirmButton
                  key={a.action}
                  label={a.label}
                  className={styles.actionBtn}
                  onConfirm={() => onAction(p, a.action)}
                />
              ) : (
                <Button key={a.action} size="sm" onClick={() => onAction(p, a.action)}>{a.label}</Button>
              ),
            )}
            {forceRollback ? (
              <ConfirmButton
                label="Forzar revert (pisa la edición manual)"
                className={styles.actionBtn}
                onConfirm={() => onAction(p, "rollback", true)}
              />
            ) : null}
          </div>
        </td>
      </tr>
      {expanded ? (
        <tr className={styles.detailRow}>
          <td colSpan={6}>
            <div className={styles.detail}>
              <p><strong>Racional:</strong> {p.rationale}</p>
              {p.evidence.length > 0 ? <p><strong>Evidencia:</strong> {p.evidence.join(" · ")}</p> : null}
              {p.proposed_content ? (
                <pre className={styles.pre}>{p.proposed_content}</pre>
              ) : null}
              {canEvaluateProposal(p.artifact_type, p.status) ? (
                <div className={styles.actions}>
                  <Button size="sm" variant="secondary" onClick={() => onEvaluateFitness(p)}>
                    Evaluar fitness (before/after)
                  </Button>
                </div>
              ) : null}
              {p.notes.length > 0 ? (
                <div className={styles.notes}>
                  {p.notes.map((n, i) => (
                    <div key={i} className={styles.note}>
                      <span className={styles.noteMeta}>{formatDateTime(n.ts)} · {n.actor}</span>
                      <span>{n.text}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {p.snapshot_info ? (
                <p className={styles.cellSub}>snapshot: {JSON.stringify(p.snapshot_info)}</p>
              ) : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

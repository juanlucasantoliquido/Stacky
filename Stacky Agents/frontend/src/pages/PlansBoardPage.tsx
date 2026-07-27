/**
 * Plan 128 — Tablero de evolución de planes (solo lectura).
 *
 * Visible solo cuando STACKY_PLANS_BOARD_ENABLED=true (gate en App.tsx).
 * La página JAMÁS ejecuta nada: muestra estado del pipeline
 * proponer→criticar→implementar→supervisar por plan, y ofrece una acción
 * sugerida COPIABLE al portapapeles (el operador la pega y ejecuta él mismo).
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  PlansBoard,
  PlansPipeline,
  type PlanCommitDto,
  type PlansBoardDetailDto,
  type RunPipelineActionResponse,
} from "../api/endpoints";
import {
  ESTADO_CHIP,
  buildCopyPayload,
  estadoChip,
  filterPlans,
  type BoardFilters,
  type EstadoPlan,
  type PlanCardDto,
  type SuggestedAction,
} from "../plansBoard/model";
// Plan 196 — acciones HITL del pipeline (helpers puros, testeados sin DOM).
import ConfirmButton from "../components/ConfirmButton";
import { useModelCatalog } from "../hooks/useModelCatalog";
import {
  ACTION_LABEL,
  RUNTIME_ACTION_NOTE,
  allowedActionsForCard,
  buildRunPayload,
  effortsForModel,
  type PipelineAction,
} from "../plansBoard/actions";
import styles from "./PlansBoardPage.module.css";

const ESTADOS: (EstadoPlan | "TODOS")[] = [
  "TODOS",
  "PROPUESTO",
  "CRITICADO",
  "IMPLEMENTADO",
  "IMPLEMENTADO_PARCIAL",
  "APROBADO",
  "SIN_ESTADO",
];

// Plan 237 — etapas de triage. El ORDEN lo fija el backend (triage_order); acá
// solo se ofrece el filtro y la etiqueta legible.
const ETAPAS: string[] = [
  "TODOS",
  "SIN_IMPLEMENTAR",
  "SIN_CRITICAR",
  "SIN_DOCUMENTO",
  "SIN_SUPERVISAR",
  "COMPLETADO",
];

const ETAPA_LABEL: Record<string, string> = {
  SIN_IMPLEMENTAR: "Sin implementar",
  SIN_CRITICAR: "Sin criticar",
  SIN_DOCUMENTO: "Sin documento",
  SIN_SUPERVISAR: "Sin supervisar",
  COMPLETADO: "Completado",
};

function CopyButton({
  action,
  variant,
  copiedKey,
  onCopy,
}: {
  action: SuggestedAction;
  variant: "primary" | "natural";
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}) {
  const text = variant === "primary" ? buildCopyPayload(action) : action.natural_language;
  const key = `${variant}:${text}`;
  const label = variant === "primary" ? "📋" : "💬";
  const isCopied = copiedKey === key;
  return (
    <button
      type="button"
      className={styles.copyBtn}
      title={variant === "primary" ? "Copiar comando/acción" : "Copiar en lenguaje natural"}
      onClick={(ev) => {
        ev.stopPropagation();
        onCopy(text, key);
      }}
    >
      {isCopied ? "Copiado ✓" : label}
    </button>
  );
}

export default function PlansBoardPage() {
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<EstadoPlan | "TODOS">("TODOS");
  const [soloPendientesPush, setSoloPendientesPush] = useState(false);
  const [soloSinSupervisar, setSoloSinSupervisar] = useState(false);
  const [bucket, setBucket] = useState<string>("TODOS"); // Plan 237 — filtro por etapa
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);

  // Plan 196 — estado del panel de acciones.
  const [actionModel, setActionModel] = useState("");
  const [actionEffort, setActionEffort] = useState("");
  const [proposeIdea, setProposeIdea] = useState("");
  const [lastLaunch, setLastLaunch] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false); // C10 — guard anti doble-click
  const queryClient = useQueryClient();

  const boardQuery = useQuery({
    queryKey: ["plans-board-list"],
    queryFn: () => PlansBoard.list(),
    retry: false,
  });

  const detailQuery = useQuery({
    queryKey: ["plans-board-detail", selectedNumber],
    queryFn: () => PlansBoard.detail(selectedNumber as number),
    enabled: selectedNumber !== null,
    retry: false,
  });

  // Plan 196 — historial de corridas. Carga on-mount + refresco manual del
  // operador; cero sondeo periódico (G9). El comentario evita nombrar la API
  // prohibida porque el criterio binario del plan es un grep sobre este archivo.
  const runsQuery = useQuery({
    queryKey: ["plans-pipeline-runs"],
    queryFn: () => PlansPipeline.runs(),
    retry: false,
  });

  const commitsQuery = useQuery({
    queryKey: ["plans-board-commits", selectedNumber],
    queryFn: () => PlansPipeline.commits(selectedNumber as number),
    enabled: selectedNumber !== null,
    retry: false,
  });

  const { catalog } = useModelCatalog();
  const claudeCat = catalog.claude_code_cli;

  // Inicializa modelo/effort con los defaults del catálogo vivo (159) —
  // cero listas hardcodeadas en este archivo (KPI-2).
  useEffect(() => {
    if (!claudeCat) return;
    setActionModel((m) => m || claudeCat.default_model || "");
    setActionEffort((e) => e || claudeCat.default_effort || "high");
  }, [claudeCat]);

  // Si al cambiar de modelo el effort deja de ser válido, cae al primero válido.
  const availableEfforts = effortsForModel(claudeCat, actionModel);
  useEffect(() => {
    if (availableEfforts.length === 0) return;
    if (!availableEfforts.some((e) => e.id === actionEffort)) {
      setActionEffort(availableEfforts[0].id);
    }
  }, [actionModel, availableEfforts, actionEffort]);

  const pipelineBusy = runsQuery.data?.busy === true;
  const actionsAvailable = runsQuery.data?.ok === true;

  const launch = (action: PipelineAction, planNumber: number | null) => {
    if (launching) return;
    setLaunching(true);
    void PlansPipeline.run(
      buildRunPayload(action, planNumber, proposeIdea, actionModel, actionEffort)
    )
      .then((r) => {
        if (r.ok && r.data?.ok && r.data.execution_id) {
          setLastLaunch(
            `Corrida #${r.data.execution_id} lanzada: ${r.data.prompt_line ?? action}`
          );
        } else {
          const err = (r.errorBody ?? {}) as Partial<RunPipelineActionResponse>;
          setLastLaunch(
            `No se lanzó (${r.status}): ${err.error ?? "error desconocido"}` +
              (err.message ? ` — ${err.message}` : "")
          );
        }
      })
      .catch((e) => setLastLaunch(`No se lanzó: ${String(e)}`))
      .finally(() => {
        setLaunching(false);
        void queryClient.invalidateQueries({ queryKey: ["plans-pipeline-runs"] });
        void queryClient.invalidateQueries({ queryKey: ["plans-board-list"] });
      });
  };

  const handleCopy = (text: string, key: string) => {
    try {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          setCopyFailed(false);
          setCopiedKey(key);
          window.setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 1500);
        })
        .catch(() => setCopyFailed(true));
    } catch {
      setCopyFailed(true);
    }
  };

  useEffect(() => {
    if (!copyFailed) return;
    const t = window.setTimeout(() => setCopyFailed(false), 2000);
    return () => window.clearTimeout(t);
  }, [copyFailed]);

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setSelectedNumber(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const board = boardQuery.data;
  const filters: BoardFilters = { texto, estado, soloPendientesPush, soloSinSupervisar, bucket };
  const filtered = useMemo(() => (board ? filterPlans(board.plans, filters) : []), [board, texto, estado, soloPendientesPush, soloSinSupervisar, bucket]);

  if (boardQuery.isLoading) {
    return (
      <div className={styles.root}>
        <p className={styles.loading}>Cargando planes…</p>
      </div>
    );
  }

  if (boardQuery.isError || !board) {
    return (
      <div className={styles.root}>
        <div className={styles.errorBanner}>
          <span>No se pudo cargar el tablero de planes.</span>
          <button type="button" className={styles.retryBtn} onClick={() => boardQuery.refetch()}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const gitAvailable = board.git_available;

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>🧭 Planes</h2>
        <span className={styles.subtitle}>
          Tablero de solo lectura del pipeline proponer → criticar → implementar → supervisar.
        </span>
      </div>

      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroCard}>
          <span className={styles.heroLabel}>Próximo Nº libre</span>
          <span className={styles.heroValue}>{board.next_free_number}</span>
        </div>
        {(Object.keys(ESTADO_CHIP) as EstadoPlan[]).map((key) => (
          <div key={key} className={styles.chipCard} style={{ borderColor: ESTADO_CHIP[key].color }}>
            <span className={styles.chipDot} style={{ background: ESTADO_CHIP[key].color }} />
            <span>{ESTADO_CHIP[key].label}</span>
            <strong>{board.totals[key] ?? 0}</strong>
          </div>
        ))}
        {gitAvailable && (
          <div className={styles.heroCard}>
            <span className={styles.heroLabel}>⬆️ Sin push</span>
            <span className={styles.heroValue}>{board.totals.unpushed ?? 0}</span>
          </div>
        )}
        {(board.totals.duplicados ?? 0) > 0 && (
          <div className={`${styles.heroCard} ${styles.heroWarn}`}>
            <span className={styles.heroLabel}>⚠️ Duplicados</span>
            <span className={styles.heroValue}>{board.totals.duplicados}</span>
          </div>
        )}
        <button type="button" className={styles.refreshBtn} onClick={() => boardQuery.refetch()}>
          ↻ Refrescar
        </button>
      </div>

      {/* Filtros */}
      <div className={styles.filters}>
        <input
          className={styles.filterInput}
          placeholder="Buscar por número, título o slug…"
          value={texto}
          onChange={(ev) => setTexto(ev.target.value)}
        />
        <select className={styles.filterSelect} value={estado} onChange={(ev) => setEstado(ev.target.value as EstadoPlan | "TODOS")}>
          {ESTADOS.map((e) => (
            <option key={e} value={e}>
              {e === "TODOS" ? "Todos los estados" : ESTADO_CHIP[e].label}
            </option>
          ))}
        </select>
        {/* Plan 237 — filtro por etapa de triage (el orden lo fija el backend) */}
        <select className={styles.filterSelect} value={bucket} onChange={(ev) => setBucket(ev.target.value)}>
          {ETAPAS.map((b) => (
            <option key={b} value={b}>
              {b === "TODOS" ? "Todas las etapas" : ETAPA_LABEL[b]}
            </option>
          ))}
        </select>
        <label className={styles.filterCheck} title={gitAvailable ? undefined : "sin datos de git"}>
          <input
            type="checkbox"
            checked={soloPendientesPush}
            disabled={!gitAvailable}
            onChange={(ev) => setSoloPendientesPush(ev.target.checked)}
          />
          Solo pendientes de push
        </label>
        <label className={styles.filterCheck}>
          <input type="checkbox" checked={soloSinSupervisar} onChange={(ev) => setSoloSinSupervisar(ev.target.checked)} />
          Solo sin supervisar
        </label>
      </div>

      {/* Plan 196 — panel de acciones HITL. Se auto-oculta si el backend no las
          expone (flag OFF -> 404): la página queda idéntica a la del Plan 128. */}
      {actionsAvailable && (
        <div className={styles.actionsPanel}>
          <div className={styles.actionsRow}>
            <span className={styles.actionsLabel}>Modelo</span>
            <select
              className={styles.actionsSelect}
              value={actionModel}
              onChange={(ev) => setActionModel(ev.target.value)}
            >
              {(claudeCat?.models ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <span className={styles.actionsLabel}>Esfuerzo</span>
            <select
              className={styles.actionsSelect}
              value={actionEffort}
              onChange={(ev) => setActionEffort(ev.target.value)}
            >
              {availableEfforts.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.label}
                </option>
              ))}
            </select>
            <span className={styles.actionsLabel} title={RUNTIME_ACTION_NOTE}>
              Runtime: Claude Code CLI
            </span>
          </div>
          <div className={styles.actionsRow}>
            <input
              className={styles.actionsInput}
              placeholder="Idea para el próximo plan (opcional)"
              value={proposeIdea}
              onChange={(ev) => setProposeIdea(ev.target.value)}
            />
            <ConfirmButton
              label={ACTION_LABEL.proponer}
              className={styles.actionBtn}
              disabled={pipelineBusy || launching}
              onConfirm={() => launch("proponer", null)}
            />
            {pipelineBusy && (
              <span className={styles.busyChip}>
                Corrida #{runsQuery.data?.running_execution_id} en curso — el pipeline
                corre de a una
              </span>
            )}
            {runsQuery.data?.working_tree?.dirty === true && (
              <span className={styles.wipChip}>
                WIP: {runsQuery.data.working_tree.changes} cambios sin commitear en el
                repo — las corridas commitean por pathspec; revisá antes de confirmar
              </span>
            )}
          </div>
          {lastLaunch && <div className={styles.actionsNote}>{lastLaunch}</div>}
        </div>
      )}

      {/* Tabla / empty state */}
      {!board.docs_dir_found || board.plans.length === 0 ? (
        <p className={styles.empty}>No se encontraron docs de planes en este deploy</p>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nº</th>
                <th>Título</th>
                <th>Etapa</th>
                <th>Estado</th>
                <th>Juez</th>
                <th>Supervisión</th>
                <th>Push</th>
                <th>Acción sugerida</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((card: PlanCardDto) => {
                const chip = estadoChip(card);
                return (
                  <tr key={`${card.number}-${card.filename}`} className={styles.row} onClick={() => setSelectedNumber(card.number)}>
                    <td>
                      {card.number_str}
                      {card.duplicate && <span className={styles.dupBadge}>DUP</span>}
                    </td>
                    <td className={styles.titleCell}>
                      <div>{card.title}</div>
                      <div className={styles.subCell}>
                        {[card.version ? `v${card.version}` : null, card.fecha].filter(Boolean).join(" · ")}
                      </div>
                    </td>
                    {/* Plan 237 — etapa de triage calculada por el backend */}
                    <td>{ETAPA_LABEL[card.triage_bucket] ?? card.triage_bucket}</td>
                    <td>
                      <span className={styles.stateChip} style={{ background: chip.color }}>
                        {chip.label}
                      </span>
                    </td>
                    <td>{card.veredicto ?? "—"}</td>
                    <td>
                      {card.ledger === null
                        ? "—"
                        : card.ledger.doc_drift === true
                          ? "⚠️ drift"
                          : `✅ ${card.ledger.veredicto}`}
                    </td>
                    <td>{card.unpushed === null ? "—" : card.unpushed ? "⬆️ pendiente" : "✓"}</td>
                    <td className={styles.actionCell}>
                      <span>{card.suggested_action.label}</span>
                      <CopyButton action={card.suggested_action} variant="primary" copiedKey={copiedKey} onCopy={handleCopy} />
                      <CopyButton action={card.suggested_action} variant="natural" copiedKey={copiedKey} onCopy={handleCopy} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {copyFailed && <div className={styles.copyFailBanner}>No se pudo copiar</div>}

      {/* Plan 196 — historial de corridas del pipeline (refresco manual, G9). */}
      {actionsAvailable && (
        <div className={styles.runsSection}>
          <div className={styles.actionsRow}>
            <strong>Corridas del pipeline</strong>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: ["plans-pipeline-runs"] });
                void queryClient.invalidateQueries({ queryKey: ["plans-board-list"] });
              }}
            >
              ↻ Refrescar
            </button>
          </div>
          <div className={styles.runsList}>
            {(runsQuery.data?.runs ?? []).length === 0 ? (
              <span className={styles.actionsNote}>Todavía no se lanzó ninguna corrida.</span>
            ) : (
              (runsQuery.data?.runs ?? []).map((r) => (
                <div key={r.id} className={styles.runRow}>
                  <span>#{r.id}</span>
                  <span>{r.action ?? "—"}</span>
                  <span>{r.plan_number ?? "—"}</span>
                  <span>{r.model ?? "—"}</span>
                  <span>{r.effort ?? "—"}</span>
                  <span className={styles.runStatus}>{r.status}</span>
                  <span>{r.started_at ?? "—"}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Drawer de detalle */}
      {selectedNumber !== null && (
        <div className={styles.drawerOverlay} onClick={() => setSelectedNumber(null)}>
          <div className={styles.drawer} onClick={(ev) => ev.stopPropagation()}>
            <button type="button" className={styles.drawerClose} onClick={() => setSelectedNumber(null)}>
              ✕
            </button>
            {detailQuery.isLoading && <p>Cargando detalle…</p>}
            {detailQuery.data && (
              <DrawerContent
                data={detailQuery.data}
                copiedKey={copiedKey}
                onCopy={handleCopy}
                actionsAvailable={actionsAvailable}
                actionsDisabled={pipelineBusy || launching}
                onLaunch={launch}
                commits={commitsQuery.data ?? null}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DrawerContent({
  data,
  copiedKey,
  onCopy,
  actionsAvailable,
  actionsDisabled,
  onLaunch,
  commits,
}: {
  data: PlansBoardDetailDto;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
  // Plan 196 — acciones por card + commits del doc.
  actionsAvailable: boolean;
  actionsDisabled: boolean;
  onLaunch: (action: PipelineAction, planNumber: number | null) => void;
  commits: { ok: boolean; git_available: boolean; commits: PlanCommitDto[] } | null;
}) {
  const { plan, duplicates, head_excerpt } = data;
  const cardActions = allowedActionsForCard(plan.estado, plan.ledger?.doc_drift ?? null);
  return (
    <div>
      <h3>
        Plan {plan.number_str} — {plan.title}
      </h3>
      <p className={styles.subCell}>
        Estado: {plan.estado} · Efectivo: {plan.estado_efectivo}
        {plan.version ? ` · v${plan.version}` : ""}
        {plan.fecha ? ` · ${plan.fecha}` : ""}
      </p>
      <p>{plan.suggested_action.label}</p>
      <div className={styles.drawerCopyRow}>
        <CopyButton action={plan.suggested_action} variant="primary" copiedKey={copiedKey} onCopy={onCopy} />
        <CopyButton action={plan.suggested_action} variant="natural" copiedKey={copiedKey} onCopy={onCopy} />
      </div>
      {/* Plan 196 — acciones permitidas para el estado de ESTE plan (§4.3). */}
      {actionsAvailable && cardActions.length > 0 && (
        <div className={styles.actionsRow}>
          {cardActions.map((a) => (
            <ConfirmButton
              key={a}
              label={ACTION_LABEL[a]}
              className={styles.actionBtn}
              disabled={actionsDisabled}
              onConfirm={() => onLaunch(a, plan.number)}
            />
          ))}
        </div>
      )}
      {/* Plan 196 — commits del doc (git log read-only, on-demand). */}
      {commits && (
        <div className={styles.commitsList}>
          {commits.git_available === false ? (
            <span>Sin git disponible en esta instalación</span>
          ) : (
            commits.commits.map((c) => (
              <span key={c.hash}>
                {c.hash} — {c.date} — {c.subject}
              </span>
            ))
          )}
        </div>
      )}
      {duplicates.length > 0 && (
        <div className={styles.dupWarning}>
          ⚠️ Número duplicado por: {duplicates.map((d) => d.filename).join(", ")}
        </div>
      )}
      <pre className={styles.headExcerpt}>{head_excerpt}</pre>
    </div>
  );
}

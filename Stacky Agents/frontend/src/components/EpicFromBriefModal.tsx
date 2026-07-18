/**
 * Plan 38 B2 — Modal "Crear Épica desde Brief".
 *
 * Flujo: Brief → Lanzar BusinessAgent (mismo runtime selector que tickets) →
 *        Generando (polling ejecución) → Revisar output → Aprobar → Crear en ADO.
 * Human-in-the-loop: el botón "Crear épica" solo se habilita tras checkbox de aprobación.
 */
import React, { useState, useEffect, useRef } from "react";
import { Agents, ClaudeCli, Executions, Tickets, type ClaudeSessionStatus, type IntentBriefDTO } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import {
  isCliRuntime,
  openConsoleIfCliRuntime,
  runtimeDisplayLabel,
} from "../services/agentLaunch";
import AgentRuntimeSelector from "./AgentRuntimeSelector";
import ClaudeCliConfigModal from "./ClaudeCliConfigModal";
import IntentPreflightModal from "./IntentPreflightModal";
import { canGenerateEpic, shouldCloseOnBackdrop } from "../services/uiGuards";
import { clearBriefDraft, readBriefDraft, writeBriefDraft } from "../services/briefDraft";
import { useModelCatalog } from "../hooks/useModelCatalog";
import type { AgentRuntime } from "../types";
import styles from "./EpicFromBriefModal.module.css";

// Plan 159 — modelos/efforts y la matriz de validez (effort_support) vienen del
// catálogo único (useModelCatalog); ya no se declaran acá. EffortLevel se
// conserva como tipo.
type EffortLevel = "low" | "medium" | "high" | "xhigh" | "max";

interface EpicFromBriefModalProps {
  onClose: () => void;
  onCreated?: (result: { ado_id: number; title: string }) => void;
}

type Step = "brief" | "running" | "creating" | "done" | "error";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 min

/**
 * Guard anti-narración (espejo de `_looks_like_epic` en backend/api/tickets.py).
 * El BusinessAgent a veces devuelve NARRACIÓN ("Voy a leer el archivo...") en vez
 * del HTML de la épica. Publicar eso contamina ADO. Solo consideramos épica un
 * contenido con un heading (<h1>/<h2>) Y al menos un bloque <h2>RF-XXX.
 * Tolera el fence ```html ... ``` que el CLI a veces antepone.
 */
function looksLikeEpic(raw: string | null | undefined): boolean {
  if (!raw || !raw.trim()) return false;
  const fence = raw.match(/```(?:html)?\s*\n?([\s\S]*?)```/i);
  const text = fence ? fence[1] : raw;
  const hasHeading = /<h[12][^>]*>/i.test(text);
  const hasRfBlock = /<h2[^>]*>\s*RF-\s*\d/i.test(text);
  return hasHeading && hasRfBlock;
}

const EPIC_NOT_IN_OUTPUT_MSG =
  "El Agente de Negocio devolvió narración en vez del HTML de la épica " +
  "(probablemente la escribió en un archivo). Revisá la consola y reintentá " +
  "la generación.";

export default function EpicFromBriefModal({ onClose, onCreated }: EpicFromBriefModalProps) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const [step, setStep] = useState<Step>("brief");
  // Plan 136 F2 — re-hidratar el borrador de la sesión (clave por proyecto).
  const [brief, setBrief] = useState<string>(() =>
    readBriefDraft(window.sessionStorage, activeProjectName)
  );
  const [executionId, setExecutionId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [createdAdoId, setCreatedAdoId] = useState<number | null>(null);

  // Plan 42 F3 — selector de modelo y esfuerzo. Plan 159 — la lista y la matriz
  // de validez (effort_support) vienen del catálogo único.
  const { catalog } = useModelCatalog();
  const claudeModels = catalog.claude_code_cli?.models ?? [];
  const claudeEfforts = catalog.claude_code_cli?.efforts ?? [];
  const isEffortValidForModel = (effort: string, modelId: string): boolean =>
    catalog.claude_code_cli?.effort_support?.[modelId]?.includes(effort) ?? true;
  const [selectedModel, setSelectedModel] = useState<string>("claude-sonnet-5");
  const [selectedEffort, setSelectedEffort] = useState<EffortLevel>("high");
  // Plan 45 F3 — selector de tipo de work item (Epic | Issue).
  const [workItemType, setWorkItemType] = useState<"Epic" | "Issue">("Epic");
  const [issueEnabled, setIssueEnabled] = useState(false);
  // Plan 42 F6 — id de la ejecución en curso para el botón Stop.
  const [runningExecutionId, setRunningExecutionId] = useState<number | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  // Plan 136 F1 — true mientras el POST de runBrief está en vuelo (ambos caminos:
  // handleGenerate y handleApproveIntent). Bloquea el doble-submit que duplicaba
  // runs y épicas auto-publicadas en ADO.
  const [isLaunching, setIsLaunching] = useState(false);

  // Plan 55 F2 — Preview de publicación (solo-lectura).
  const [epicPreview, setEpicPreview] = useState<{
    ok: boolean;
    title: string | null;
    html: string | null;
    work_item_type: string;
    error: string | null;
    grounding_warnings: string[];
    publishable_runtime: boolean;
  } | null>(null);
  const [previewAvailable, setPreviewAvailable] = useState(true); // false si flag OFF (404)

  // Plan 41 F4 — pre-vuelo de intención.
  const [showPreflightModal, setShowPreflightModal] = useState(false);
  const [preflightIntent, setPreflightIntent] = useState<IntentBriefDTO | null>(null);
  const [preflightAutoApprovable, setPreflightAutoApprovable] = useState(false);

  // Claude Code CLI config
  const [claudeSession, setClaudeSession] = useState<ClaudeSessionStatus | null>(null);
  const [claudeChecking, setClaudeChecking] = useState(false);
  const [showClaudeConfig, setShowClaudeConfig] = useState(false);
  const claudeReady = claudeSession?.logged_in === true;
  const claudeNeedsConfig = agentRuntime === "claude_code_cli" && !claudeReady;

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);

  async function probeClaude(): Promise<boolean> {
    setClaudeChecking(true);
    try {
      const s = await ClaudeCli.session();
      setClaudeSession(s);
      return s.logged_in === true;
    } catch {
      setClaudeSession(null);
      return false;
    } finally {
      setClaudeChecking(false);
    }
  }

  function handleRuntimeChange(rt: AgentRuntime) {
    setAgentRuntime(rt);
    // Plan 42 F3 — resetear modelo a sonnet-5 (primario) si el runtime no es claude_code_cli.
    if (rt !== "claude_code_cli") {
      setSelectedModel("claude-sonnet-5");
    }
    // Plan 43 F2 — el probe se dispara vía useEffect([agentRuntime]); no abrir config automáticamente.
  }

  // Plan 43 F2 — probe silencioso al montar / al cambiar a claude_code_cli (sin abrir panel).
  useEffect(() => {
    if (agentRuntime === "claude_code_cli") {
      void probeClaude();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentRuntime]);

  // Plan 45 F3 — cargar flag de config al montar.
  useEffect(() => {
    void (async () => {
      try {
        const cfg = await Tickets.frontendConfig();
        setIssueEnabled(cfg.issue_from_brief_enabled ?? false);
      } catch {
        // Silenciar error — default a false si la config no está disponible.
        setIssueEnabled(false);
      }
    })();
  }, []);

  // Plan 43 F3 — si el modelo cambia y el effort actual no es válido, resetear a "high".
  useEffect(() => {
    if (!isEffortValidForModel(selectedEffort, selectedModel)) {
      setSelectedEffort("high");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModel]);

  // Plan 55 F2 — Fetch del preview cuando hay executionId activo.
  // Refresca cada poll cycle; si el endpoint no está disponible (flag OFF / 404), oculta la sección.
  useEffect(() => {
    if (executionId === null || !previewAvailable) return;
    let cancelled = false;
    const poll = setInterval(async () => {
      try {
        const preview = await Tickets.epicPreview(executionId, issueEnabled ? workItemType : "Epic");
        if (!cancelled) setEpicPreview(preview);
      } catch (err: unknown) {
        if (!cancelled) {
          const status = (err as { status?: number })?.status;
          if (status === 404) {
            setPreviewAvailable(false);
          }
          // Otros errores: ignorar silenciosamente (best-effort)
        }
      }
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executionId, previewAvailable, workItemType]);

  // Inicia el polling de la ejecución hasta que termine.
  function startPolling(execId: number) {
    pollStartRef.current = Date.now();
    pollRef.current = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setErrorMsg("Tiempo de espera agotado. La ejecución tardó más de 5 minutos.");
        setStep("error");
        return;
      }
      try {
        const exec = await Executions.byId(execId);
        if (exec.status !== "running" && exec.status !== "queued" && exec.status !== "preparing") {
          stopPolling();
          // Plan 41 — El backend puede haber publicado la épica de forma
          // autónoma al cerrar la run. Si ya hay sello, NO re-publicar (evita
          // épica duplicada); si hay error de publicación, mostrarlo.
          const md = (exec.metadata ?? {}) as Record<string, unknown>;
          const sealedAdoId = typeof md.epic_ado_id === "number" ? md.epic_ado_id : null;
          const publishErr = typeof md.epic_publish_error === "string" ? md.epic_publish_error : null;
          if (sealedAdoId !== null) {
            setCreatedAdoId(sealedAdoId);
            setStep("done");
            onCreated?.({ ado_id: sealedAdoId, title: "" });
            return;
          }
          if (publishErr !== null) {
            setErrorMsg(`La publicación automática de la épica falló: ${publishErr}`);
            setStep("error");
            return;
          }
          if (exec.status === "completed" || exec.status === "needs_review") {
            const html = (exec.output ?? "").trim();
            if (!html) {
              setErrorMsg("La ejecución terminó sin contenido para publicar la épica.");
              setStep("error");
              return;
            }
            // Guard anti-narración: NO publicar basura si el output no es una épica.
            // (El backend ya degrada a needs_review + epic_publish_error en el camino
            // autónomo; este chequeo cubre el caso sin sello ni error, evitando mandar
            // narración cruda al endpoint.)
            if (!looksLikeEpic(html)) {
              setErrorMsg(EPIC_NOT_IN_OUTPUT_MSG);
              setStep("error");
              return;
            }
            void publishEpic(html);
          } else {
            setErrorMsg(
              exec.error_message ?? `La ejecución terminó con estado: ${exec.status}`
            );
            setStep("error");
          }
        }
      } catch {
        // Polling fallo transitorio — continuar
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => () => stopPolling(), []);

  // Plan 136 F2 — borrador write-through: cada tecla persiste; vacío ⇒ se borra la clave.
  useEffect(() => {
    writeBriefDraft(window.sessionStorage, activeProjectName, brief);
  }, [brief, activeProjectName]);

  async function handleGenerate() {
    if (!brief.trim() || isLaunching) return;
    setIsLaunching(true);
    setErrorMsg(null);
    setRunningExecutionId(null);
    try {
      // Plan 41 F4 — enviar preflight:true para disponer el pre-vuelo.
      // Plan 42 F3 — enviar modelo y esfuerzo; modelo solo si runtime es claude_code_cli.
      const result = await Agents.runBrief({
        brief: brief.trim(),
        runtime: agentRuntime,
        project: activeProjectName,
        model: agentRuntime === "claude_code_cli" ? selectedModel : undefined,
        effort: selectedEffort,
        work_item_type: issueEnabled ? workItemType : "Epic",
        preflight: true,
      });

      // Plan 41 F4 — si el backend devolvió stage:preflight, mostrar modal sin comenzar la ejecución.
      if (result.stage === "preflight" && result.intent) {
        setPreflightIntent(result.intent);
        setPreflightAutoApprovable(result.auto_approvable ?? false);
        setShowPreflightModal(true);
        // Si auto_approvable, re-llamar inmediatamente con approved:true (sin mostrar el modal).
        if (result.auto_approvable) {
          setShowPreflightModal(false);
          await handleApproveIntent(undefined);
        }
        return;
      }

      // Backend no dispuso preflight (flag OFF o runtime no disponible) — proceder normalmente.
      const execId = result.execution_id;
      if (!execId) {
        setErrorMsg("No se pudo lanzar el Agente de Negocio (ejecución sin ID).");
        setStep("error");
        return;
      }
      setExecutionId(execId);
      setRunningExecutionId(execId); // Plan 42 F6 — habilitar botón Stop
      setStep("running");
      // Abrir consola in-page para runtimes CLI (igual que tickets).
      if (isCliRuntime(agentRuntime)) {
        openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      }
      startPolling(execId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "No se pudo lanzar el Agente de Negocio.");
      setStep("error");
    } finally {
      setIsLaunching(false);
    }
  }

  // Plan 41 F4 — re-llamar runBrief con approved:true (+ corrections si las hay).
  async function handleApproveIntent(corrections: string | undefined) {
    if (!brief.trim() || isLaunching) return;
    setIsLaunching(true);
    setErrorMsg(null);
    setStep("running");
    setRunningExecutionId(null);
    try {
      const result = await Agents.runBrief({
        brief: brief.trim(),
        runtime: agentRuntime,
        project: activeProjectName,
        model: agentRuntime === "claude_code_cli" ? selectedModel : undefined,
        effort: selectedEffort,
        work_item_type: issueEnabled ? workItemType : "Epic",
        approved: true,
        corrections,
      });

      const execId = result.execution_id;
      if (!execId) {
        setErrorMsg("No se pudo lanzar el Agente de Negocio (ejecución sin ID).");
        setStep("error");
        return;
      }
      setExecutionId(execId);
      setRunningExecutionId(execId);
      setShowPreflightModal(false);
      // Abrir consola in-page para runtimes CLI.
      if (isCliRuntime(agentRuntime)) {
        openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      }
      startPolling(execId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "No se pudo lanzar el Agente de Negocio.");
      setStep("error");
    } finally {
      setIsLaunching(false);
    }
  }

  // Plan 42 F6 — Cancelar ejecución en curso.
  async function handleStop() {
    if (!runningExecutionId || isCancelling) return;
    if (!window.confirm("¿Cancelar la generación en curso?")) return;
    setIsCancelling(true);
    try {
      await Executions.cancel(runningExecutionId);
      stopPolling();
      setRunningExecutionId(null);
      setErrorMsg("Generación cancelada por el operador.");
      setStep("error");
    } catch (e: unknown) {
      const status = (e as { status?: number })?.status;
      if (status === 409) {
        // La ejecución ya terminó — no es error grave.
        setRunningExecutionId(null);
      } else {
        setErrorMsg("No se pudo cancelar la ejecución. Verificá el estado en el panel de runs.");
      }
    } finally {
      setIsCancelling(false);
    }
  }

  // Auto-publicación: al terminar la run, la épica se crea en ADO directamente,
  // sin paso de aprobación manual. El backend deriva el título del contenido.
  async function publishEpic(html: string) {
    setStep("creating");
    setErrorMsg(null);
    try {
      const res = await Tickets.createEpicFromBrief({
        title: "",
        description_html: html,
        brief: brief.trim(),
        project_name: activeProjectName ?? undefined,
        confirm: true,
      });
      setCreatedAdoId(res.ado_id);
      clearBriefDraft(window.sessionStorage, activeProjectName);
      setStep("done");
      onCreated?.({ ado_id: res.ado_id, title: res.title });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "Error al crear la épica en ADO.");
      setStep("error");
    }
  }

  function handleBackdrop(e: React.MouseEvent) {
    if (e.target !== e.currentTarget) return;
    // dirty: hay brief tipeado o el flujo ya avanzó (running/creating/error).
    // En "done" no hay nada que perder: el backdrop vuelve a cerrar.
    const dirty = step !== "done" && (brief.trim().length > 0 || step !== "brief");
    const busy = isLaunching || step === "running" || step === "creating";
    if (shouldCloseOnBackdrop({ dirty, busy })) onClose();
  }

  const canGenerate = canGenerateEpic({
    step,
    briefEmpty: brief.trim().length === 0,
    isLaunching,
    claudeGateBlocked: agentRuntime === "claude_code_cli" && !claudeReady,
  });

  return (
    <div className={styles.overlay} onClick={handleBackdrop}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Nueva Épica desde Brief">
        <header className={styles.header}>
          <h2 className={styles.title}>Nueva Épica desde Brief</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">✕</button>
        </header>

        {/* PASO 1: Ingresar brief + elegir runtime */}
        {step === "brief" && (
          <div className={styles.body}>
            <div className={styles.runtimeSection}>
              <AgentRuntimeSelector
                value={agentRuntime}
                onChange={handleRuntimeChange}
                disabled={false}
                claudeNeedsConfig={claudeNeedsConfig}
              />
              <p className={styles.runtimeLabel}>
                El Agente de Negocio correrá con:{" "}
                <strong>{runtimeDisplayLabel(agentRuntime)}</strong>
              </p>
            </div>

            {/* Plan 43 F2 — aviso no intrusivo; el probe es automático y silencioso. */}
            {agentRuntime === "claude_code_cli" && claudeChecking && (
              <div className={styles.warning}><span>Verificando sesión Claude Code…</span></div>
            )}
            {agentRuntime === "claude_code_cli" && !claudeChecking && !claudeReady && (
              <div className={styles.warning}>
                <span>
                  Claude Code no está listo.{" "}
                  {claudeSession?.error ? `(${claudeSession.error})` : ""}
                </span>
                <button
                  className={styles.inlineBtn}
                  onClick={() => setShowClaudeConfig(true)}
                  type="button"
                >
                  ⚙ Configurar
                </button>
              </div>
            )}

            {/* Plan 42 F3 — Selector de modelo (solo claude_code_cli) y esfuerzo */}
            <div className={styles.runtimeSection}>
              <label className={styles.label}>
                Modelo
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={agentRuntime !== "claude_code_cli"}
                  title={agentRuntime !== "claude_code_cli" ? "El selector de modelo solo aplica a Claude Code CLI" : undefined}
                >
                  {claudeModels.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </label>
              <label className={styles.label}>
                Esfuerzo
                <select
                  value={selectedEffort}
                  onChange={(e) => setSelectedEffort(e.target.value as EffortLevel)}
                  disabled={agentRuntime !== "claude_code_cli"}
                  title={agentRuntime !== "claude_code_cli" ? "El selector de esfuerzo solo aplica a Claude Code CLI" : undefined}
                >
                  {claudeEfforts.map((eff) => {
                    const valid = isEffortValidForModel(eff.id, selectedModel);
                    return (
                      <option key={eff.id} value={eff.id} disabled={!valid}>
                        {eff.label}{!valid ? " (no disponible para este modelo)" : ""}
                      </option>
                    );
                  })}
                </select>
              </label>
              {issueEnabled && (
                <label className={styles.label}>
                  Tipo de work item
                  <select
                    value={workItemType}
                    onChange={(e) => setWorkItemType(e.target.value as "Epic" | "Issue")}
                  >
                    <option value="Epic">Épica</option>
                    <option value="Issue">Issue</option>
                  </select>
                </label>
              )}
            </div>

            <label className={styles.label}>
              Brief del negocio (texto libre)
              <textarea
                className={styles.textarea}
                rows={8}
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="Pegá la transcripción, notas de reunión o brief del cliente…"
                autoFocus
              />
            </label>

            <p className={styles.hint}>
              El Agente de Negocio va a descomponer el brief y proponer una Épica estructurada
              (título + bloques RF-XXX en HTML), que se creará automáticamente en ADO al
              terminar la generación.
            </p>

            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
              <button
                className={styles.primaryBtn}
                onClick={handleGenerate}
                disabled={!canGenerate}
                title={
                  agentRuntime === "claude_code_cli" && !claudeReady
                    ? "Configurá Claude Code antes de continuar"
                    : undefined
                }
              >
                {isLaunching ? "Lanzando…" : "▶ Generar épica con Agente de Negocio"}
              </button>
            </footer>
          </div>
        )}

        {/* PASO 2: Generando — ejecución en curso */}
        {step === "running" && (
          <div className={styles.body}>
            <p className={styles.status}>
              El Agente de Negocio está procesando el brief
              {isCliRuntime(agentRuntime) ? " (podés seguirlo en la consola)" : ""}…
            </p>
            <div className={styles.spinner} aria-label="Cargando" />
            {executionId !== null && (
              <p className={styles.hint}>Ejecución #{executionId}</p>
            )}

            {/* Plan 55 F2 — Vista previa de publicación (solo-lectura) */}
            {previewAvailable && epicPreview !== null && (
              <div className={styles.previewSection}>
                <div className={styles.previewHeader}>Vista previa de publicación</div>
                {epicPreview.ok ? (
                  <>
                    {epicPreview.title && (
                      <div className={styles.previewTitle}>{epicPreview.title}</div>
                    )}
                    <div
                      className={styles.previewHtml}
                      // eslint-disable-next-line react/no-danger
                      dangerouslySetInnerHTML={{ __html: epicPreview.html ?? "" }}
                    />
                    {epicPreview.grounding_warnings.length > 0 && (
                      <div className={styles.previewWarnings}>
                        Advertencias de grounding: {epicPreview.grounding_warnings.join("; ")}
                      </div>
                    )}
                    {!epicPreview.publishable_runtime && (
                      <div className={styles.publishDisabledHint}>
                        Este runtime no auto-publica. Para publicar automáticamente, seleccioná Claude Code CLI.
                      </div>
                    )}
                  </>
                ) : (
                  <div className={styles.previewError}>
                    {epicPreview.error === "empty_output"
                      ? "El agente aún no produjo contenido publicable…"
                      : epicPreview.error === "epic_not_in_output"
                      ? "El agente narró en vez de devolver HTML de épica. Si falla la publicación, revisá el output."
                      : `No se pudo generar el preview: ${epicPreview.error ?? "error desconocido"}`}
                  </div>
                )}
              </div>
            )}

            {/* Plan 42 F6 — botón Stop visible solo mientras hay ejecución en curso */}
            {runningExecutionId !== null && (
              <footer className={styles.footer}>
                <button
                  className={styles.cancelBtn}
                  onClick={handleStop}
                  disabled={isCancelling}
                  type="button"
                >
                  {isCancelling ? "Cancelando…" : "Detener generación"}
                </button>
              </footer>
            )}
          </div>
        )}

        {/* PASO 3: Creando épica en ADO (automático, sin aprobación manual) */}
        {step === "creating" && (
          <div className={styles.body}>
            <p className={styles.status}>Creando épica en ADO…</p>
            <div className={styles.spinner} aria-label="Cargando" />
          </div>
        )}

        {/* PASO 4: Éxito */}
        {step === "done" && createdAdoId !== null && (
          <div className={styles.body}>
            <p className={styles.successNote}>
              Épica ADO-{createdAdoId} creada correctamente. El Analista Funcional puede tomarla desde el board.
            </p>
            <footer className={styles.footer}>
              <button className={styles.primaryBtn} onClick={onClose}>Cerrar</button>
            </footer>
          </div>
        )}

        {/* Error */}
        {step === "error" && (
          <div className={styles.body}>
            <p className={styles.errorMsg}>{errorMsg}</p>
            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={() => { setErrorMsg(null); setStep("brief"); }}>
                Volver
              </button>
              <button className={styles.primaryBtn} onClick={onClose}>Cerrar</button>
            </footer>
          </div>
        )}
      </div>

      {showClaudeConfig && (
        <ClaudeCliConfigModal
          onClose={() => setShowClaudeConfig(false)}
          onConfigured={() => { void probeClaude(); }}
        />
      )}

      {/* Plan 41 F4 — Modal de pre-vuelo de intención. */}
      {showPreflightModal && preflightIntent && (
        <IntentPreflightModal
          intent={preflightIntent}
          busy={isLaunching}
          onApprove={(corrections) => {
            void handleApproveIntent(corrections);
          }}
          onCancel={() => {
            setShowPreflightModal(false);
            setPreflightIntent(null);
            setPreflightAutoApprovable(false);
          }}
        />
      )}
    </div>
  );
}

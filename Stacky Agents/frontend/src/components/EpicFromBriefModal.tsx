/**
 * Plan 38 B2 — Modal "Crear Épica desde Brief".
 *
 * Flujo: Brief → Lanzar BusinessAgent (mismo runtime selector que tickets) →
 *        Generando (polling ejecución) → Revisar output → Aprobar → Crear en ADO.
 * Human-in-the-loop: el botón "Crear épica" solo se habilita tras checkbox de aprobación.
 */
import React, { useState, useEffect, useRef } from "react";
import { Agents, ClaudeCli, Executions, Tickets, type ClaudeSessionStatus } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import {
  isCliRuntime,
  openConsoleIfCliRuntime,
  runtimeDisplayLabel,
} from "../services/agentLaunch";
import AgentRuntimeSelector from "./AgentRuntimeSelector";
import ClaudeCliConfigModal from "./ClaudeCliConfigModal";
import type { AgentRuntime } from "../types";
import styles from "./EpicFromBriefModal.module.css";

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
  const [brief, setBrief] = useState("");
  const [executionId, setExecutionId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [createdAdoId, setCreatedAdoId] = useState<number | null>(null);

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

  async function handleRuntimeChange(rt: AgentRuntime) {
    setAgentRuntime(rt);
    if (rt === "claude_code_cli") {
      const ready = claudeSession ? claudeReady : await probeClaude();
      if (!ready) setShowClaudeConfig(true);
    }
  }

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

  async function handleGenerate() {
    if (!brief.trim()) return;
    setErrorMsg(null);
    setStep("running");
    try {
      const result = await Agents.runBrief({
        brief: brief.trim(),
        runtime: agentRuntime,
        project: activeProjectName,
      });
      const execId = result.execution_id;
      setExecutionId(execId);
      // Abrir consola in-page para runtimes CLI (igual que tickets).
      if (isCliRuntime(agentRuntime)) {
        openConsoleIfCliRuntime(agentRuntime, result, (id) => setCodexConsoleExecution(id, false));
      }
      startPolling(execId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "No se pudo lanzar el Agente de Negocio.");
      setStep("error");
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
      setStep("done");
      onCreated?.({ ado_id: res.ado_id, title: res.title });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "Error al crear la épica en ADO.");
      setStep("error");
    }
  }

  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  const canGenerate = brief.trim().length > 0 && step === "brief"
    && !(agentRuntime === "claude_code_cli" && !claudeReady);

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

            {agentRuntime === "claude_code_cli" && !claudeReady && !claudeChecking && (
              <div className={styles.warning}>
                <span>
                  Claude Code no está configurado.{" "}
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
            {agentRuntime === "claude_code_cli" && claudeChecking && (
              <div className={styles.warning}><span>Verificando Claude Code…</span></div>
            )}

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
                ▶ Generar épica con Agente de Negocio
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
    </div>
  );
}

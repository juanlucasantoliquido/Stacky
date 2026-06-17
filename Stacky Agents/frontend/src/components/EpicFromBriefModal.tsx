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

type Step = "brief" | "running" | "review" | "creating" | "done" | "error";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 min

export default function EpicFromBriefModal({ onClose, onCreated }: EpicFromBriefModalProps) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const [step, setStep] = useState<Step>("brief");
  const [brief, setBrief] = useState("");
  const [executionId, setExecutionId] = useState<number | null>(null);
  const [outputHtml, setOutputHtml] = useState("");
  const [title, setTitle] = useState("");
  const [approved, setApproved] = useState(false);
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
          if (exec.status === "completed" || exec.status === "needs_review") {
            setOutputHtml(exec.output ?? "");
            setTitle("");
            setApproved(false);
            setStep("review");
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

  async function handleCreate() {
    if (!approved || !outputHtml.trim()) return;
    setStep("creating");
    setErrorMsg(null);
    try {
      const res = await Tickets.createEpicFromBrief({
        title: title.trim() || "Épica generada desde brief",
        description_html: outputHtml.trim(),
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
              (título + bloques RF-XXX en HTML). Vas a revisar y aprobar el resultado antes
              de que se cree en ADO.
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

        {/* PASO 3: Revisar output y aprobar */}
        {step === "review" && (
          <div className={styles.body}>
            <p className={styles.successNote}>
              El Agente de Negocio completó la generación. Revisá el resultado y corregí si es necesario.
            </p>

            <label className={styles.label}>
              Título de la Épica
              <input
                className={styles.input}
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Derivá el título del contenido generado…"
              />
            </label>

            <label className={styles.label}>
              Contenido generado (editable)
              <textarea
                className={styles.textarea}
                rows={12}
                value={outputHtml}
                onChange={(e) => setOutputHtml(e.target.value)}
              />
            </label>

            <label className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={approved}
                onChange={(e) => setApproved(e.target.checked)}
              />
              <span>He revisado el contenido generado y apruebo la creación de esta épica en ADO.</span>
            </label>

            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={() => { stopPolling(); setStep("brief"); }}>
                Volver
              </button>
              <button
                className={styles.primaryBtn}
                onClick={handleCreate}
                disabled={!approved || !outputHtml.trim()}
              >
                Crear épica en ADO
              </button>
            </footer>
          </div>
        )}

        {/* PASO 4: Creando en ADO */}
        {step === "creating" && (
          <div className={styles.body}>
            <p className={styles.status}>Creando épica en ADO…</p>
            <div className={styles.spinner} aria-label="Cargando" />
          </div>
        )}

        {/* PASO 5: Éxito */}
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

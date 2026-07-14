/**
 * Plan 131 F7 — Modal "Resolver incidencia" (intake multimodal → análisis
 * unificado → preview → publish). Espeja la mecánica de EpicFromBriefModal
 * (steps, polling, selector de runtime/modelo/effort para Claude).
 */
import React, { useEffect, useRef, useState } from "react";
import { Incidents, Executions, type IncidentDTO, type IncidentPreviewDTO } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { isCliRuntime, openConsoleIfCliRuntime, runtimeDisplayLabel } from "../services/agentLaunch";
import AgentRuntimeSelector from "./AgentRuntimeSelector";
import {
  validateFiles,
  canAnalyze,
  summarizeRelatedEpic,
  pickResumableIncident,
  type IncidentStatusDTO,
} from "../incidents/incidentModel";
import type { AgentRuntime } from "../types";
import styles from "./IncidentResolverModal.module.css";

type Step = "intake" | "running" | "preview" | "publishing" | "done" | "error";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

const CLAUDE_MODELS: { value: string; label: string }[] = [
  { value: "claude-sonnet-4-6", label: "Sonnet 4.6 (recomendado)" },
  { value: "claude-opus-4-8", label: "Opus 4.8 (mayor calidad, más lento)" },
  { value: "claude-haiku-4-5", label: "Haiku 4.5 (más rápido)" },
];

type EffortLevel = "low" | "medium" | "high" | "xhigh" | "max";
const CLAUDE_EFFORTS: EffortLevel[] = ["low", "medium", "high", "xhigh", "max"];

interface IncidentResolverModalProps {
  onClose: () => void;
}

export default function IncidentResolverModal({ onClose }: IncidentResolverModalProps) {
  const agentRuntime = useWorkbench((s) => s.agentRuntime);
  const setAgentRuntime = useWorkbench((s) => s.setAgentRuntime);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const [status, setStatus] = useState<IncidentStatusDTO | null>(null);
  const [step, setStep] = useState<Step>("intake");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<number | null>(null);
  const [preview, setPreview] = useState<IncidentPreviewDTO | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [selectedModel, setSelectedModel] = useState("claude-sonnet-4-6");
  const [selectedEffort, setSelectedEffort] = useState<EffortLevel>("high");

  const [overrideEpicId, setOverrideEpicId] = useState("");
  const [publishWithoutEpic, setPublishWithoutEpic] = useState(false);
  const [approved, setApproved] = useState(false);

  const [publishResult, setPublishResult] = useState<{
    tracker_id: string;
    url: string;
    epic_id: number | null;
    epic_link_mode: string;
    doc_path: string | null;
    warnings: string[];
  } | null>(null);

  // [ADICIÓN ARQUITECTO] Reanudación de incidencias en curso.
  const [resumable, setResumable] = useState<IncidentDTO | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);

  useEffect(() => {
    void (async () => {
      try {
        const s = await Incidents.status();
        setStatus(s);
      } catch {
        setStatus(null);
      }
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const res = await Incidents.list();
        const pick = pickResumableIncident(res.incidents ?? []);
        setResumable(pick);
      } catch {
        setResumable(null);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => stopPolling(), []);

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function handleFilesSelected(selected: FileList | File[]) {
    const list = Array.from(selected);
    const merged = [...files, ...list];
    setFiles(merged);
    if (status) {
      const result = validateFiles(merged.map((f) => ({ name: f.name, size: f.size })), status);
      setValidationErrors(result.errors);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    if (e.dataTransfer.files?.length) handleFilesSelected(e.dataTransfer.files);
  }

  function removeFile(idx: number) {
    const merged = files.filter((_, i) => i !== idx);
    setFiles(merged);
    if (status) {
      setValidationErrors(validateFiles(merged.map((f) => ({ name: f.name, size: f.size })), status).errors);
    }
  }

  async function handleAnalyze() {
    setErrorMsg(null);
    try {
      const created = await Incidents.create(text.trim(), files);
      const newIncidentId = created.incident.id;
      setIncidentId(newIncidentId);

      const runResult = await Incidents.runAnalysis({
        incident_id: newIncidentId,
        runtime: agentRuntime,
        project: activeProjectName,
        model: agentRuntime === "claude_code_cli" ? selectedModel : undefined,
        effort: selectedEffort,
      });
      setExecutionId(runResult.execution_id);
      setStep("running");
      if (isCliRuntime(agentRuntime)) {
        openConsoleIfCliRuntime(agentRuntime, runResult, (id) => setCodexConsoleExecution(id, false));
      }
      startPolling(newIncidentId, runResult.execution_id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "No se pudo lanzar el análisis de la incidencia.");
      setStep("error");
    }
  }

  function startPolling(incId: string, execId: number) {
    pollStartRef.current = Date.now();
    pollRef.current = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setErrorMsg("Tiempo de espera agotado (5 minutos).");
        setStep("error");
        return;
      }
      try {
        const exec = await Executions.byId(execId);
        if (exec.status !== "running" && exec.status !== "queued" && exec.status !== "preparing") {
          stopPolling();
          await loadPreview(incId, execId);
        }
      } catch {
        // fallo transitorio de polling — continuar
      }
    }, POLL_INTERVAL_MS);
  }

  async function loadPreview(incId: string, execId: number) {
    try {
      const p = await Incidents.preview(execId, incId);
      setPreview(p);
      if (p.ok) {
        setStep("preview");
      } else {
        setErrorMsg(
          p.error === "incident_not_in_output"
            ? "El agente narró en vez de devolver el desglose HTML. Revisá la consola y reintentá."
            : `No se pudo generar el preview: ${p.error ?? "error desconocido"}`
        );
        setStep("error");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "No se pudo obtener el preview de la incidencia.");
      setStep("error");
    }
  }

  async function handleResume() {
    if (!resumable) return;
    setIncidentId(resumable.id);
    setExecutionId(resumable.execution_id);
    setResumable(null);
    if (resumable.status === "analizando" && resumable.execution_id !== null) {
      setStep("running");
      startPolling(resumable.id, resumable.execution_id);
    } else if (resumable.status === "analizada" && resumable.execution_id !== null) {
      await loadPreview(resumable.id, resumable.execution_id);
    }
  }

  async function handlePublish() {
    if (!incidentId || executionId === null || !approved) return;
    setStep("publishing");
    setErrorMsg(null);
    try {
      const payload: Parameters<typeof Incidents.publish>[0] = {
        incident_id: incidentId,
        execution_id: executionId,
        confirm: true,
      };
      if (publishWithoutEpic) {
        payload.override_epic_id = null;
      } else if (overrideEpicId.trim()) {
        payload.override_epic_id = Number(overrideEpicId.trim());
      }
      const res = await Incidents.publish(payload);
      setPublishResult({
        tracker_id: res.tracker_id,
        url: res.url,
        epic_id: res.epic_id,
        epic_link_mode: res.epic_link_mode,
        doc_path: res.doc_path,
        warnings: res.warnings ?? [],
      });
      setStep("done");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErrorMsg(msg || "Error al publicar la incidencia en el tracker.");
      setStep("error");
    }
  }

  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  if (status !== null && !status.enabled) {
    return null;
  }

  const canSubmit = status !== null && canAnalyze(text, files) && validationErrors.length === 0;

  return (
    <div className={styles.overlay} onClick={handleBackdrop}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Resolver incidencia">
        <header className={styles.header}>
          <h2 className={styles.title}>🚑 Resolver incidencia</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">✕</button>
        </header>

        {resumable && step === "intake" && (
          <div className={styles.resumeBanner}>
            <span>Tenés una incidencia en curso ({resumable.title || resumable.id}).</span>
            <button className={styles.inlineBtn} onClick={() => void handleResume()} type="button">
              Retomar
            </button>
          </div>
        )}

        {step === "intake" && (
          <div className={styles.body}>
            <div className={styles.runtimeSection}>
              <AgentRuntimeSelector value={agentRuntime} onChange={(rt: AgentRuntime) => setAgentRuntime(rt)} />
              <p className={styles.runtimeLabel}>
                El análisis correrá con: <strong>{runtimeDisplayLabel(agentRuntime)}</strong>
              </p>
            </div>

            {agentRuntime === "claude_code_cli" && (
              <div className={styles.runtimeSection}>
                <label className={styles.label}>
                  Modelo
                  <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                    {CLAUDE_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </label>
                <label className={styles.label}>
                  Esfuerzo
                  <select value={selectedEffort} onChange={(e) => setSelectedEffort(e.target.value as EffortLevel)}>
                    {CLAUDE_EFFORTS.map((eff) => (
                      <option key={eff} value={eff}>{eff}</option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            <label className={styles.label}>
              Texto libre de la incidencia
              <textarea
                className={styles.textarea}
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Describí qué se rompe, a quién impacta, cuándo empezó…"
                autoFocus
              />
            </label>

            <div
              className={styles.dropzone}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <input
                type="file"
                multiple
                onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
              />
              <p className={styles.hint}>Arrastrá capturas o logs acá, o hacé click para elegir archivos.</p>
            </div>

            {files.length > 0 && (
              <ul className={styles.fileList}>
                {files.map((f, idx) => (
                  <li key={`${f.name}-${idx}`}>
                    {f.name} ({Math.round(f.size / 1024)} KB)
                    <button type="button" className={styles.inlineBtn} onClick={() => removeFile(idx)}>
                      Quitar
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {validationErrors.length > 0 && (
              <div className={styles.errorMsg}>
                {validationErrors.map((err) => <div key={err}>{err}</div>)}
              </div>
            )}

            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
              <button
                className={styles.primaryBtn}
                onClick={() => void handleAnalyze()}
                disabled={!canSubmit}
              >
                ▶ Analizar
              </button>
            </footer>
          </div>
        )}

        {step === "running" && (
          <div className={styles.body}>
            <p className={styles.status}>
              El Analista de Incidencias está procesando
              {isCliRuntime(agentRuntime) ? " (podés seguirlo en la consola)" : ""}…
            </p>
            <div className={styles.spinner} aria-label="Cargando" />
            {executionId !== null && <p className={styles.hint}>Ejecución #{executionId}</p>}
          </div>
        )}

        {step === "preview" && preview && (
          <div className={styles.body}>
            {preview.title && <div className={styles.previewTitle}>{preview.title}</div>}
            <div
              className={styles.previewHtml}
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{ __html: preview.html ?? "" }}
            />
            <div className={styles.previewSection}>
              <div className={styles.previewHeader}>Épica relacionada</div>
              <p>{summarizeRelatedEpic(preview)}</p>
              <label className={styles.label}>
                Override épica (id)
                <input
                  type="number"
                  value={overrideEpicId}
                  onChange={(e) => setOverrideEpicId(e.target.value)}
                  disabled={publishWithoutEpic}
                />
              </label>
              <label className={styles.label}>
                <input
                  type="checkbox"
                  checked={publishWithoutEpic}
                  onChange={(e) => setPublishWithoutEpic(e.target.checked)}
                />
                Publicar sin épica
              </label>
            </div>

            <label className={styles.label}>
              <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
              Revisé el desglose y confirmo publicarlo en el tracker
            </label>

            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
              <button
                className={styles.primaryBtn}
                onClick={() => void handlePublish()}
                disabled={!approved}
              >
                Publicar en el tracker
              </button>
            </footer>
          </div>
        )}

        {step === "publishing" && (
          <div className={styles.body}>
            <p className={styles.status}>Publicando en el tracker…</p>
            <div className={styles.spinner} aria-label="Cargando" />
          </div>
        )}

        {step === "done" && publishResult && (
          <div className={styles.body}>
            <p className={styles.successNote}>
              Issue publicado:{" "}
              <a href={publishResult.url} target="_blank" rel="noreferrer">
                {publishResult.tracker_id}
              </a>
              {" — "}
              enlace a épica: {publishResult.epic_link_mode}
            </p>
            {publishResult.doc_path && (
              <p className={styles.hint}>Doc del incidente: {publishResult.doc_path}</p>
            )}
            {publishResult.warnings.length > 0 && (
              <div className={styles.previewWarnings}>
                Advertencias: {publishResult.warnings.join("; ")}
              </div>
            )}
            <footer className={styles.footer}>
              <button className={styles.primaryBtn} onClick={onClose}>Cerrar</button>
            </footer>
          </div>
        )}

        {step === "error" && (
          <div className={styles.body}>
            <p className={styles.errorMsg}>{errorMsg}</p>
            <footer className={styles.footer}>
              <button className={styles.cancelBtn} onClick={() => { setErrorMsg(null); setStep("intake"); }}>
                Volver
              </button>
              <button className={styles.primaryBtn} onClick={onClose}>Cerrar</button>
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}

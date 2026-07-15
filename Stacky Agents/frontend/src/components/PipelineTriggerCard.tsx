/**
 * Plan 72 F4 — PipelineTriggerCard
 *
 * Card HITL para disparar y monitorear un pipeline CI de GitLab.
 *
 * Comportamiento:
 *  - Lee flag STACKY_PIPELINE_TRIGGER_ENABLED de GET /api/harness-flags.
 *  - Si flag OFF: botón deshabilitado con tooltip.
 *  - Click botón → triggerPreview → modal con ref + last_pipeline + warning.
 *  - "Disparar" en modal → triggerPipeline con confirm: true.
 *  - Polling cada 5s (backoff a 15s tras 3 intentos) hasta status terminal.
 *  - Cancela polling al desmontar.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CIPipeline,
  HarnessFlags,
  type CIPreviewResponse,
  type CIMonitorResponse,
} from "../api/endpoints";
import Toast, { type ToastState } from "./Toast";

interface Props {
  project: string;
  ref: string;
  itemId?: string;
}

const TERMINAL_STATUSES = new Set(["success", "failed", "canceled", "skipped"]);

export default function PipelineTriggerCard({ project, ref, itemId = "" }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [preview, setPreview] = useState<CIPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [monitorData, setMonitorData] = useState<CIMonitorResponse | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [activePipelineId, setActivePipelineId] = useState<string | null>(null);
  const pollCountRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Leer flag desde /api/harness-flags (mismo endpoint que HarnessFlagsPanel, C2/C6')
  const { data: flagsData } = useQuery({
    queryKey: ["harness-flags"],
    queryFn: () => HarnessFlags.list(),
    staleTime: 30_000,
  });

  const flagEnabled = !!flagsData?.flags?.find(
    (f) => f.key === "STACKY_PIPELINE_TRIGGER_ENABLED"
  )?.value;

  // Limpiar al desmontar
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const showToast = (msg: string, kind: "info" | "error" = "info") => {
    setToast({ variant: kind === "error" ? "error" : "success", body: msg });
    setTimeout(() => { if (mountedRef.current) setToast(null); }, 5000);
  };

  // ── Preview (read-only, no dispara) ──────────────────────────────────────
  const handlePreview = useCallback(async () => {
    if (!flagEnabled || !ref) return;
    setPreviewLoading(true);
    try {
      const data = await CIPipeline.preview(project, ref);
      if (!mountedRef.current) return;
      setPreview(data);
      setModalOpen(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error al obtener preview";
      showToast(msg, "error");
    } finally {
      if (mountedRef.current) setPreviewLoading(false);
    }
  }, [project, ref, flagEnabled]);

  // ── Polling del pipeline ──────────────────────────────────────────────────
  const schedulePoll = useCallback(
    (pipelineId: string, attempt: number) => {
      const delay = attempt < 3 ? 5_000 : 15_000;
      pollTimerRef.current = setTimeout(async () => {
        if (!mountedRef.current) return;
        try {
          const data = await CIPipeline.monitor(project, pipelineId);
          if (!mountedRef.current) return;
          setMonitorData(data);
          if (!TERMINAL_STATUSES.has(data.status)) {
            schedulePoll(pipelineId, attempt + 1);
          } else {
            showToast(`Pipeline ${pipelineId}: ${data.status}`, data.status === "success" ? "info" : "error");
          }
        } catch {
          // error de polling — seguir intentando si no es terminal
          if (!mountedRef.current) return;
          schedulePoll(pipelineId, attempt + 1);
        }
      }, delay);
    },
    [project]
  );

  // ── Trigger HITL ─────────────────────────────────────────────────────────
  const handleTrigger = useCallback(async () => {
    if (!flagEnabled || !preview) return;
    setTriggerLoading(true);
    try {
      // confirm: true es OBLIGATORIO — riel HITL absoluto
      const result = await CIPipeline.trigger(project, ref, preview.last_pipeline?.sha ?? "", itemId, true);
      if (!mountedRef.current) return;
      setModalOpen(false);
      if (result.status === "reused" || result.pipeline_id) {
        showToast(`Pipeline reusado: ${result.pipeline_id}`, "info");
      } else {
        showToast(`Pipeline ${result.id} disparado (${result.status})`, "info");
        setActivePipelineId(result.id);
        pollCountRef.current = 0;
        schedulePoll(result.id, 0);
      }
    } catch (err: unknown) {
      if (!mountedRef.current) return;
      const msg = err instanceof Error ? err.message : "Error al disparar pipeline";
      showToast(msg, "error");
    } finally {
      if (mountedRef.current) setTriggerLoading(false);
    }
  }, [project, ref, itemId, preview, flagEnabled, schedulePoll]);

  return (
    <div style={{ border: "1px solid #ccc", borderRadius: 6, padding: "12px 16px", maxWidth: 480 }}>
      <h4 style={{ margin: "0 0 8px" }}>Disparar Pipeline CI</h4>

      {/* Status del pipeline activo */}
      {activePipelineId && monitorData && (
        <div style={{ marginBottom: 8, fontSize: 13, color: monitorData.status === "success" ? "green" : "inherit" }}>
          Pipeline <strong>{activePipelineId}</strong>: {monitorData.status}
          {monitorData.web_url && (
            <> &mdash; <a href={monitorData.web_url} target="_blank" rel="noreferrer">Ver en GitLab</a></>
          )}
        </div>
      )}

      {/* Toast */}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}

      {/* Botón principal */}
      <button
        onClick={handlePreview}
        disabled={!flagEnabled || previewLoading}
        title={!flagEnabled ? "Flag STACKY_PIPELINE_TRIGGER_ENABLED está OFF. Actívala en Ajustes > Arnés." : undefined}
        style={{ opacity: !flagEnabled ? 0.5 : 1, cursor: !flagEnabled ? "not-allowed" : "pointer" }}
      >
        {previewLoading ? "Cargando preview..." : "Disparar pipeline"}
      </button>

      {/* Modal HITL de confirmación */}
      {modalOpen && preview && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
        }}>
          <div style={{
            background: "#fff", borderRadius: 8, padding: 24,
            width: 420, boxShadow: "0 4px 24px rgba(0,0,0,.2)",
          }}>
            <h3 style={{ marginTop: 0 }}>Confirmar disparo de pipeline</h3>
            <p><strong>Proyecto:</strong> {project}</p>
            <p><strong>Ref:</strong> {preview.ref} <em>({preview.kind})</em></p>

            {preview.last_pipeline ? (
              <p style={{ fontSize: 13, color: "#555" }}>
                Ultimo pipeline: <strong>{preview.last_pipeline.id}</strong> ({preview.last_pipeline.status})
                {preview.last_pipeline.web_url && (
                  <> &mdash; <a href={preview.last_pipeline.web_url} target="_blank" rel="noreferrer">ver</a></>
                )}
              </p>
            ) : (
              <p style={{ fontSize: 13, color: "#888" }}>Sin pipeline previo en este ref.</p>
            )}

            {preview.would_reuse && (
              <p style={{ fontSize: 13, color: "#e65100", background: "#fff3e0", padding: "6px 8px", borderRadius: 4 }}>
                Idempotencia: ya existe un pipeline reciente para este ref+sha.
                Se devolvera el ID existente sin disparar uno nuevo.
              </p>
            )}

            <p style={{
              fontSize: 13, fontWeight: 600, color: "#b71c1c",
              background: "#ffebee", padding: "6px 8px", borderRadius: 4,
            }}>
              Vas a disparar un pipeline real en GitLab sobre {project} / {preview.ref}. Confirmar para continuar.
            </p>

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button
                onClick={handleTrigger}
                disabled={triggerLoading}
                style={{ background: "#c62828", color: "#fff", border: "none", borderRadius: 4, padding: "8px 18px", cursor: "pointer" }}
              >
                {triggerLoading ? "Disparando..." : "Disparar"}
              </button>
              <button
                onClick={() => setModalOpen(false)}
                style={{ background: "#f5f5f5", border: "1px solid #ccc", borderRadius: 4, padding: "8px 18px", cursor: "pointer" }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

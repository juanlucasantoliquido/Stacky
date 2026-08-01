/**
 * Plan 113 — Botón "Lanzar Documentador" (1-click, sin formularios). Dispara el run,
 * hace polling del estado mientras corre y muestra el panel de resultado al terminar.
 */
import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Docs } from "../../api/endpoints";
import { normalizeOperatorNote, summarizeDocumenterStatus } from "../../docs/documenterModel";
import { DocumenterResultPanel } from "./DocumenterResultPanel";
import { useWorkbench } from "../../store/workbench";

interface Props {
  projectName?: string;
  /** Plan 284 — gatea el campo de nota (STACKY_DOCS_OPERATOR_NOTE_ENABLED). */
  noteEnabled?: boolean;
  /** Plan 284 — tope de la nota; viaja desde el backend, no se hardcodea (C18). */
  noteMaxChars?: number;
}

export function DocumenterButton({
  projectName,
  noteEnabled = true,
  noteMaxChars = 4000,
}: Props) {
  const [runId, setRunId] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [note, setNote] = useState("");  // Plan 284 — nota libre del operador
  const [approving, setApproving] = useState(false);  // Plan 284 F5.3
  const [deciding, setDeciding] = useState(false);
  const [decided, setDecided] = useState<"keep" | "discard" | null>(null);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);

  const { data: status } = useQuery({
    queryKey: ["documenter-status", runId],
    queryFn: () => Docs.documenterStatus(runId as string),
    enabled: !!runId,
    refetchInterval: (query) => {
      const st = query.state.data;
      const sum = summarizeDocumenterStatus(st);
      // Plan 284 — seguimos poleando mientras espera aprobación: apenas el
      // operador aprueba, el run vuelve a "running" y la UI tiene que seguirlo.
      return sum.running || sum.uiState === "awaiting_approval" ? 1500 : false;
    },
  });

  // Fix "no me hizo nada" (Tarea 2) — consola en vivo: el Documentador corre en
  // background sin devolver un execution_id sincrónico (a diferencia de DevOps/QA),
  // así que enganchamos el CodexConsoleDock reactivamente a medida que el polling
  // de status va viendo el execution_id del modo en curso (mismo dock que usan
  // DevOpsAgentSection/PipelineDoctorPanel/AgentLaunchModal/TicketBoard).
  const currentExecutionId = status?.current_execution_id ?? null;
  useEffect(() => {
    if (currentExecutionId != null) {
      setCodexConsoleExecution(currentExecutionId);
    }
  }, [currentExecutionId, setCodexConsoleExecution]);

  const launch = useCallback(async () => {
    setLaunching(true);
    setLaunchError(null);
    setDecided(null);
    try {
      const res = await Docs.documenterRun(projectName, normalizeOperatorNote(note));
      if (res.ok && res.run_id) {
        setRunId(res.run_id);
      } else {
        setLaunchError(res.error || "No se pudo lanzar el Documentador.");
      }
    } catch (e) {
      setLaunchError(String(e));
    } finally {
      setLaunching(false);
    }
  }, [projectName, note]);

  const decide = useCallback(
    async (action: "keep" | "discard") => {
      if (!runId) return;
      setDeciding(true);
      try {
        await Docs.documenterDecide(runId, action);
        setDecided(action);
      } finally {
        setDeciding(false);
      }
    },
    [runId]
  );

  // Plan 284 F5.3 — human-in-the-loop: aprobar o cancelar el paso a escribir.
  const approve = useCallback(
    async (ok: boolean) => {
      if (!runId) return;
      setApproving(true);
      try {
        await Docs.documenterStageApprove(runId, ok);
      } catch (e) {
        setLaunchError(String(e));
      } finally {
        setApproving(false);
      }
    },
    [runId]
  );

  const summary = summarizeDocumenterStatus(status);

  return (
    <div>
      {/* Plan 284 F2.1 — indicaciones libres del operador. Vacío ⇒ flujo 1-click
          intacto. NO se limpia al terminar: el operador suele reintentar afinando. */}
      {noteEnabled ? (
        <>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Indicaciones extra para el Documentador (opcional). Ej: 'enfocate en el módulo de pipelines y no toques la doc de DevOps'."
            maxLength={noteMaxChars}
            disabled={launching || summary.running}
            aria-label="Nota para el Documentador"
            rows={3}
            style={{ width: "100%", resize: "vertical", marginBottom: 6 }}
          />
          <div style={{ fontSize: "0.8em", color: "var(--text-secondary)", marginBottom: 6 }}>
            {note.length}/{noteMaxChars}
          </div>
        </>
      ) : null}
      <button type="button" onClick={launch} disabled={launching || summary.running}>
        {summary.running
          ? `Documentando… ${summary.currentMode ?? ""}`
          : launching
            ? "Lanzando…"
            : "Lanzar Documentador"}
      </button>
      {launchError ? <p style={{ color: "#a00" }}>{launchError}</p> : null}
      {status && summary.uiState !== "running" && summary.uiState !== "unknown" ? (
        <DocumenterResultPanel
          status={status}
          onDecide={decide}
          onApprove={approve}
          approving={approving}
          deciding={deciding}
          decided={decided}
        />
      ) : null}
    </div>
  );
}

export default DocumenterButton;

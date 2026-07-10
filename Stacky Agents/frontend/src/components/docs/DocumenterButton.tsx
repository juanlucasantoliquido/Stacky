/**
 * Plan 113 — Botón "Lanzar Documentador" (1-click, sin formularios). Dispara el run,
 * hace polling del estado mientras corre y muestra el panel de resultado al terminar.
 */
import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Docs } from "../../api/endpoints";
import { summarizeDocumenterStatus } from "../../docs/documenterModel";
import { DocumenterResultPanel } from "./DocumenterResultPanel";

interface Props {
  projectName?: string;
}

export function DocumenterButton({ projectName }: Props) {
  const [runId, setRunId] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [decided, setDecided] = useState<"keep" | "discard" | null>(null);

  const { data: status } = useQuery({
    queryKey: ["documenter-status", runId],
    queryFn: () => Docs.documenterStatus(runId as string),
    enabled: !!runId,
    refetchInterval: (query) => {
      const st = query.state.data;
      const sum = summarizeDocumenterStatus(st);
      return sum.running ? 1500 : false;
    },
  });

  const launch = useCallback(async () => {
    setLaunching(true);
    setLaunchError(null);
    setDecided(null);
    try {
      const res = await Docs.documenterRun(projectName);
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
  }, [projectName]);

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

  const summary = summarizeDocumenterStatus(status);

  return (
    <div>
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
          deciding={deciding}
          decided={decided}
        />
      ) : null}
    </div>
  );
}

export default DocumenterButton;

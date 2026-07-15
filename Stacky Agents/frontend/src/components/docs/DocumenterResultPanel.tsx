/**
 * Plan 113 — Panel de resultado del Documentador: resumen (health delta, escritos,
 * saltados, degradado), diff_stat y acciones Conservar/Descartar. La UI NUNCA
 * ejecuta el merge: al conservar muestra el comando `git merge <branch>` copiable.
 *
 * Plan 137 F6 — suma (con V2 OFF, backend manda [] y estos bloques no rinden
 * nada, panel idéntico al de hoy): archivos escritos con preview + citas
 * verificadas, saltados con razón en castellano, modos sin trabajo por
 * short-circuit, e historial de corridas anteriores (lazy, un solo fetch).
 */
import { useState } from "react";
import { Docs } from "../../api/endpoints";
import type { DocumenterStatusResponse } from "../../api/endpoints";
import {
  summarizeDocumenterStatus,
  buildFilesView,
  buildSkippedView,
  buildRunsView,
  type DocumenterRunRow,
} from "../../docs/documenterModel";

interface Props {
  status: DocumenterStatusResponse;
  onDecide: (action: "keep" | "discard") => void;
  deciding: boolean;
  decided: "keep" | "discard" | null;
}

export function DocumenterResultPanel({ status, onDecide, deciding, decided }: Props) {
  const s = summarizeDocumenterStatus(status);
  const [showMerge, setShowMerge] = useState(false);
  const branch = s.branch;
  const filesView = buildFilesView(status);
  const skippedView = buildSkippedView(status);
  const modesSkipped = status.modes_skipped ?? [];

  const [runsView, setRunsView] = useState<DocumenterRunRow[] | null>(null);
  const [runsFetched, setRunsFetched] = useState(false);

  function handleRunsToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    // C4/A1 — un solo fetch, disparado recién al ABRIR el detalle por primera
    // vez (onToggle también dispara al cerrar; lo ignoramos).
    if (!e.currentTarget.open || runsFetched) return;
    setRunsFetched(true);
    Docs.documenterRuns()
      .then((res) => setRunsView(buildRunsView(res)))
      .catch(() => setRunsView([]));
  }

  return (
    <div style={{ border: "1px solid var(--color-border, #ccc)", borderRadius: 8, padding: 12, marginTop: 8 }}>
      <h4 style={{ margin: "0 0 8px" }}>Resultado del Documentador</h4>
      <p style={{ margin: "2px 0" }}>Salud: {s.healthDelta || "—"}</p>
      <p style={{ margin: "2px 0" }}>
        {s.writtenCount} archivo(s) escritos · {s.skippedCount} saltado(s)
        {s.degraded ? " · (modo carpeta-sombra: no es repo git, revisá a mano)" : ""}
      </p>
      {s.errorMessage ? (
        // Fix "no me hizo nada" (Tarea 1) — antes un run completado sin escribir
        // nada era 100% silencioso (0 escritos, 0 saltados, ningún aviso). Ahora
        // el motivo real (ejecución en error, o el modelo no siguió el formato
        // <<<DOC ...>>>) queda visible acá.
        <p style={{ margin: "4px 0", color: "#a00", fontWeight: 600 }}>
          El Documentador no escribió nada: {s.errorMessage}
        </p>
      ) : null}
      {s.diffStat ? (
        <pre style={{ maxHeight: 160, overflow: "auto", background: "rgba(0,0,0,0.04)", padding: 8 }}>
          {s.diffStat}
        </pre>
      ) : null}

      {/* Plan 137 F6 — con V2 OFF filesView/skippedView vienen [] y este bloque
          no rinde nada (panel idéntico al de antes de este plan). */}
      {filesView.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          {filesView.map((f) => (
            <details key={f.path} style={{ marginBottom: 4 }}>
              <summary>
                {f.path} · {f.action}
                {f.citationsLabel ? ` · ${f.citationsLabel}` : ""}
              </summary>
              <pre style={{ maxHeight: 240, overflow: "auto" }}>{f.preview}</pre>
              {f.citationsBad.length > 0 ? (
                <p style={{ color: "#a00", margin: "4px 0" }}>
                  Citas no verificables: {f.citationsBad.join(", ")}
                </p>
              ) : null}
            </details>
          ))}
        </div>
      ) : null}

      {skippedView.length > 0 ? (
        <ul style={{ marginTop: 8 }}>
          {skippedView.map((sk) => (
            <li key={sk.path}>
              {sk.path} — {sk.label}
            </li>
          ))}
        </ul>
      ) : null}

      {modesSkipped.length > 0 ? (
        <p style={{ margin: "4px 0", opacity: 0.8 }}>
          Modos sin trabajo: {modesSkipped.map((m) => m.mode).join(", ")}
        </p>
      ) : null}

      {decided === "keep" ? (
        <div>
          <p style={{ color: "green" }}>Rama conservada: {branch}</p>
          {branch ? (
            <>
              <button type="button" onClick={() => setShowMerge((v) => !v)}>
                {showMerge ? "Ocultar" : "Ver comando de merge"}
              </button>
              {showMerge ? (
                <pre style={{ background: "rgba(0,0,0,0.06)", padding: 8 }}>{`git merge ${branch}`}</pre>
              ) : null}
            </>
          ) : null}
        </div>
      ) : decided === "discard" ? (
        <p style={{ color: "#a00" }}>Rama descartada.</p>
      ) : s.degraded ? (
        <p style={{ opacity: 0.7 }}>Sin rama que conservar/descartar (carpeta-sombra).</p>
      ) : (
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" disabled={deciding} onClick={() => onDecide("keep")}>
            Conservar rama
          </button>
          <button type="button" disabled={deciding} onClick={() => onDecide("discard")}>
            Descartar
          </button>
        </div>
      )}

      {/* C4 — el historial (plan 137 F4) no puede quedar sin superficie de UI.
          Lazy: cero fetch hasta que el operador abre el detalle. */}
      <details style={{ marginTop: 12 }} onToggle={handleRunsToggle}>
        <summary>Corridas anteriores</summary>
        {runsView === null ? (
          runsFetched ? (
            <p style={{ opacity: 0.7 }}>Cargando…</p>
          ) : null
        ) : runsView.length === 0 ? (
          <p style={{ opacity: 0.7 }}>Sin corridas registradas.</p>
        ) : (
          <ul>
            {runsView.map((r) => (
              <li key={r.runId}>
                {r.runId} · {r.state} · {r.branch} · {r.countsLabel}
                {r.citationsLabel ? ` · ${r.citationsLabel}` : ""}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}

export default DocumenterResultPanel;

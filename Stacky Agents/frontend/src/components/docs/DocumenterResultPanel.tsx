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
  buildStagesView,
  buildVerdictView,
  buildRadiographyView,
  formatSkipReason,
  type DocumenterRunRow,
} from "../../docs/documenterModel";

interface Props {
  status: DocumenterStatusResponse;
  onDecide: (action: "keep" | "discard") => void;
  deciding: boolean;
  decided: "keep" | "discard" | null;
  /** Plan 284 F5.3 — aprobar/cancelar el paso a IMPLEMENTAR (human-in-the-loop). */
  onApprove?: (approve: boolean) => void;
  approving?: boolean;
}

/** Plan 284 — tokens REALES del tema. No existen tokens `--color-*`: usarlos
 *  no pinta nada. */
const TONE_COLOR: Record<string, string> = {
  ok: "var(--success)",
  warn: "var(--accent)",
  bad: "var(--danger)",
};

export function DocumenterResultPanel({
  status, onDecide, deciding, decided, onApprove, approving,
}: Props) {
  const s = summarizeDocumenterStatus(status);
  const [showMerge, setShowMerge] = useState(false);
  const branch = s.branch;
  const filesView = buildFilesView(status);
  const skippedView = buildSkippedView(status);
  const modesSkipped = status.modes_skipped ?? [];
  // Plan 284 F7 — vistas puras (testeadas en documenterModel.test.ts).
  const stagesView = buildStagesView(status);
  const verdictView = buildVerdictView(status);
  const radiography = buildRadiographyView(status);
  const awaitingApproval = status.state === "awaiting_approval";
  const paperStages = (status.stages ?? []).filter(
    (st) => st.artifact && st.artifact.trim().length > 0
  );

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
    <div style={{ border: "1px solid var(--border, #ccc)", borderRadius: 8, padding: 12, marginTop: 8 }}>
      {/* Plan 284 F7 — el VEREDICTO va arriba de todo: es lo primero que el
          operador tiene que poder leer de un vistazo. */}
      {status.verdict ? (
        <div
          style={{
            borderLeft: `4px solid ${TONE_COLOR[verdictView.tone]}`,
            background: "var(--bg-panel)",
            padding: "8px 12px",
            borderRadius: 6,
            marginBottom: 10,
          }}
        >
          <strong style={{ color: TONE_COLOR[verdictView.tone] }}>{verdictView.label}</strong>
          {verdictView.detail ? (
            <div style={{ fontSize: "0.9em", color: "var(--text-primary)" }}>
              {verdictView.detail}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Etapas del pipeline, en el orden canónico. */}
      {(status.stages ?? []).length > 0 ? (
        <ol style={{ margin: "0 0 10px", paddingLeft: 18 }}>
          {stagesView.map((st) => (
            <li key={st.stage} style={{ opacity: st.state === "pending" ? 0.5 : 1 }}>
              <strong>{st.label}</strong>: {st.badge}
              {st.summary ? <span style={{ color: "var(--text-primary)" }}> — {st.summary}</span> : null}
            </li>
          ))}
        </ol>
      ) : null}

      {/* Human-in-the-loop: el operador lee el plan y su autocrítica ANTES de
          que se escriba un solo archivo, y decide. */}
      {awaitingApproval ? (
        <div style={{ border: `1px solid ${TONE_COLOR.warn}`, borderRadius: 6, padding: 10, marginBottom: 10 }}>
          <p style={{ margin: "0 0 6px" }}>
            El Documentador ya planeó y se autocriticó. <strong>Todavía no escribió nada.</strong>
          </p>
          {paperStages.map((st) => (
            <details key={st.stage} style={{ marginBottom: 4 }}>
              <summary>{st.stage}</summary>
              <pre style={{ maxHeight: 240, overflow: "auto", whiteSpace: "pre-wrap" }}>
                {st.artifact}
              </pre>
            </details>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button type="button" disabled={approving} onClick={() => onApprove?.(true)}>
              Aprobar e implementar
            </button>
            <button type="button" disabled={approving} onClick={() => onApprove?.(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : null}

      {/* Radiografía: cobertura, delta contra el run anterior y triage de tickets. */}
      {status.radiography?.enabled ? (
        <div style={{ marginBottom: 10, fontSize: "0.92em" }}>
          <div>{radiography.coverageLabel}</div>
          {radiography.deltaLabel ? (
            <div style={{ color: TONE_COLOR.ok }}>{radiography.deltaLabel}</div>
          ) : null}
          {radiography.ticketsLabel ? <div>{radiography.ticketsLabel}</div> : null}
          {radiography.uncovered.length > 0 ? (
            <details>
              <summary>{radiography.uncovered.length} módulo(s) sin documentar</summary>
              <ul>{radiography.uncovered.map((m) => <li key={m}>{m}</li>)}</ul>
            </details>
          ) : null}
        </div>
      ) : null}

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

      {/* Plan 284 F3 — los rechazados por el gate de citas van en SU PROPIA
          sección: no se pierden, se explican. */}
      {filesView.length > 0 && (status.files ?? []).some((f) => f.rejected) ? (
        <div style={{ marginTop: 8 }}>
          <strong style={{ color: TONE_COLOR.bad }}>Rechazados por citas inválidas</strong>
          <ul>
            {(status.files ?? [])
              .filter((f) => f.rejected)
              .map((f) => (
                <li key={f.path}>
                  {f.path} — {formatSkipReason(f.reject_reason ?? "")}
                </li>
              ))}
          </ul>
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

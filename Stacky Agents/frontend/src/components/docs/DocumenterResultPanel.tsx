/**
 * Plan 113 — Panel de resultado del Documentador: resumen (health delta, escritos,
 * saltados, degradado), diff_stat y acciones Conservar/Descartar. La UI NUNCA
 * ejecuta el merge: al conservar muestra el comando `git merge <branch>` copiable.
 */
import { useState } from "react";
import type { DocumenterStatusResponse } from "../../api/endpoints";
import { summarizeDocumenterStatus } from "../../docs/documenterModel";

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
    </div>
  );
}

export default DocumenterResultPanel;

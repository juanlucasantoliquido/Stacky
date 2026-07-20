/**
 * EpicChildrenPanel.tsx — Plan 59 F5: Preview y creación de hijos del Epic en ADO.
 *
 * Solo se renderiza cuando:
 *   - La flag STACKY_EPIC_DECOMPOSITION_ENABLED está ON (lo decide el backend).
 *   - Hay un Epic ya publicado (epicAdoId != null).
 *   - La run tiene output con estructura de épica parseable.
 *
 * Human-in-the-loop: nada se crea sin que el operador pulse "Crear N hijos en ADO"
 * y confirme el diálogo. El fingerprint anti-drift garantiza que lo aprobado = lo que se crea.
 */
import { useEffect, useState } from "react";
import { Tickets } from "../api/endpoints";
import { useConfirm } from "./ui";

interface ChildNode {
  work_item_type: string;
  title: string;
  html: string;
  children: { work_item_type: string; title: string; html: string }[];
}

interface PreviewData {
  enabled: boolean;
  epic_ok?: boolean;
  epic_title?: string | null;
  epic_error?: string | null;
  features: ChildNode[];
  total_children: number;
  children_error?: string | null;
  plan_fingerprint?: string;
}

interface Props {
  output: string;
  epicAdoId: number;
  projectName?: string;
}

export default function EpicChildrenPanel({ output, epicAdoId, projectName }: Props) {
  const askConfirm = useConfirm();
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState<{
    created_ids: number[];
    reused_ids: number[];
    error: string | null;
    warnings: string[];
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCreateResult(null);
    Tickets.epicChildrenPreview({ output, project_name: projectName })
      .then((res: PreviewData) => {
        if (!cancelled) setPreview(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(String(err instanceof Error ? err.message : err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [output, projectName]);

  if (loading) return null;
  if (error) return null;
  if (!preview || !preview.enabled) return null;
  if (!preview.epic_ok) return null;
  if (preview.total_children === 0) {
    return (
      <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)" }}>
        Esta épica no tiene hijos descomponibles (sin bloques RF con estructura de Feature).
      </div>
    );
  }

  const handleCreate = async () => {
    if (!(await askConfirm({
      title: "Crear hijos en ADO",
      message: `¿Crear ${preview.total_children} hijos en ADO (${preview.features.length} Feature(s) + Tasks)?\nEsta acción es idempotente: reintentar no duplica.`,
      confirmLabel: "Crear",
    }))) return;

    setCreating(true);
    setCreateResult(null);
    try {
      const res = await Tickets.createEpicChildren({
        epic_ado_id: epicAdoId,
        output,
        project_name: projectName,
        approved_fingerprint: preview.plan_fingerprint,
      });
      setCreateResult({
        created_ids: res.created_ids,
        reused_ids: res.reused_ids,
        error: res.error ?? null,
        warnings: res.warnings ?? [],
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setCreateResult({ created_ids: [], reused_ids: [], error: msg, warnings: [] });
    } finally {
      setCreating(false);
    }
  };

  const alreadyCreated = createResult != null && createResult.error == null;

  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "12px 16px" }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
        Descomposición vertical — {preview.total_children} hijos propuestos
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
        {preview.features.length} Feature(s) derivada(s) de los bloques RF de la épica:
      </div>
      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
        {preview.features.map((feat, fi) => (
          <li key={fi} style={{ marginBottom: 4 }}>
            <strong>[Feature]</strong> {feat.title}
            {feat.children.length > 0 && (
              <ul style={{ paddingLeft: 16, marginTop: 2 }}>
                {feat.children.map((task, ti) => (
                  <li key={ti}><strong>[Task]</strong> {task.title}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>

      {createResult && (
        <div style={{
          marginTop: 8, fontSize: 12, padding: "6px 8px", borderRadius: 4,
          backgroundColor: createResult.error ? "var(--danger-bg, #fff0f0)" : "var(--success-bg, #f0fff4)",
          color: createResult.error ? "var(--danger)" : "var(--success, #1a7a3f)",
        }}>
          {createResult.error
            ? `Error: ${createResult.error}`
            : `Creados: ${createResult.created_ids.length} | Ya existían: ${createResult.reused_ids.length}`}
          {createResult.warnings.length > 0 && (
            <div>
              {createResult.warnings.map((w, wi) => (
                <div key={wi}>⚠ {w}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {!alreadyCreated && (
        <button
          onClick={handleCreate}
          disabled={creating}
          style={{
            marginTop: 10,
            padding: "6px 14px",
            fontSize: 12,
            fontWeight: 600,
            cursor: creating ? "not-allowed" : "pointer",
            backgroundColor: "var(--primary, #0066cc)",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            opacity: creating ? 0.7 : 1,
          }}
        >
          {creating ? "Creando…" : `Crear ${preview.total_children} hijos en ADO`}
        </button>
      )}
    </div>
  );
}

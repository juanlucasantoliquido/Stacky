import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ProvenanceDrawer.module.css";

interface ProvenanceResponse {
  ok: boolean;
  execution_id: number;
  agent_type: string;
  ticket_id: number;
  ticket_ado_id: number | null;
  status: string;
  verdict: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  model: string | null;
  model_reason: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd_total: number | null;
  confidence: number | null;
  sources: { kind: string; label: string }[];
  chain_from: number[];
}

interface Props {
  executionId: number | null;
  open: boolean;
  onClose: () => void;
}

export default function ProvenanceDrawer({ executionId, open, onClose }: Props) {
  const [data, setData] = useState<ProvenanceResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || executionId == null) return;
    setLoading(true);
    api
      .get<ProvenanceResponse>(`/api/executions/${executionId}/provenance`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open, executionId]);

  if (!open) return null;

  return (
    <div className={styles.backdrop} onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <aside className={styles.drawer} role="dialog" aria-label="Provenance">
        <header className={styles.header}>
          <h3>ⓘ Cómo se construyó esto</h3>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className={styles.body}>
          {loading && <p className={styles.muted}>Cargando…</p>}
          {!loading && !data && <p className={styles.muted}>No hay datos.</p>}
          {data && (
            <>
              <dl className={styles.list}>
                <dt>Modelo</dt>
                <dd>{data.model ?? "(no informado)"}</dd>
                {data.model_reason && (
                  <>
                    <dt>Por qué</dt>
                    <dd>{data.model_reason}</dd>
                  </>
                )}
                <dt>Tokens</dt>
                <dd>
                  {data.tokens_in ?? "?"} entrada / {data.tokens_out ?? "?"} salida
                </dd>
                <dt>Costo</dt>
                <dd>
                  {data.cost_usd_total != null
                    ? `$${data.cost_usd_total.toFixed(4)}`
                    : "(no calculado)"}
                </dd>
                {data.confidence != null && (
                  <>
                    <dt>Confianza</dt>
                    <dd>{(data.confidence * (data.confidence <= 1 ? 100 : 1)).toFixed(0)}%</dd>
                  </>
                )}
                <dt>Duración</dt>
                <dd>
                  {data.duration_ms != null
                    ? `${(data.duration_ms / 1000).toFixed(1)}s`
                    : "—"}
                </dd>
                <dt>Verdict</dt>
                <dd>{data.verdict ?? "—"}</dd>
              </dl>

              <h4 className={styles.subheader}>Fuentes usadas</h4>
              {data.sources.length === 0 ? (
                <p className={styles.muted}>No se registraron fuentes.</p>
              ) : (
                <ul className={styles.sources}>
                  {data.sources.map((s, idx) => (
                    <li key={idx}>
                      <span className={styles.sourceKind}>{s.kind}</span>
                      <span>{s.label}</span>
                    </li>
                  ))}
                </ul>
              )}

              {data.chain_from.length > 0 && (
                <>
                  <h4 className={styles.subheader}>Encadenado a</h4>
                  <ul className={styles.sources}>
                    {data.chain_from.map((id) => (
                      <li key={id}>Ejecución #{id}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

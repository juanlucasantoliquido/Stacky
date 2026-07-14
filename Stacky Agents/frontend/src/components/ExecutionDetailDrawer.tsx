import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, Copy } from "lucide-react";
import { Executions } from "../api/endpoints";
import type { ExecutionLocalInsight } from "../api/endpoints";
import ExecutionInsightBlock from "./ExecutionInsightBlock";
import ExecutionErrorAnalysisBlock from "./ExecutionErrorAnalysisBlock";
import ContractBadge from "./ContractBadge";
import StructuredOutput from "./StructuredOutput";
import styles from "./ExecutionDetailDrawer.module.css";

interface Props {
  executionId: number | null;
  onClose: () => void;
}

function formatDuration(durationMs?: number | null): string {
  if (!durationMs || durationMs <= 0) return "-";
  const seconds = durationMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

function formatMaybeCurrency(value: unknown): string {
  if (value == null) return "-";
  const n = Number(value);
  if (Number.isFinite(n)) return `$${n.toFixed(4)}`;
  return String(value);
}

function formatTokens(value: unknown): string {
  if (value == null) return "-";
  const n = Number(value);
  if (Number.isFinite(n)) return n.toLocaleString();
  return String(value);
}

export default function ExecutionDetailDrawer({ executionId, onClose }: Props) {
  const execQ = useQuery({
    queryKey: ["execution-detail", executionId],
    queryFn: () => Executions.byId(executionId!),
    enabled: executionId != null,
  });

  const filesQ = useQuery({
    queryKey: ["execution-output-files", executionId],
    queryFn: () => Executions.outputFiles(executionId!),
    enabled: executionId != null,
  });

  const content = execQ.data;
  const metadata = (content?.metadata ?? {}) as Record<string, unknown>;
  const claudeTelemetry = (metadata.claude_telemetry ?? {}) as Record<string, unknown>;
  const usage = (claudeTelemetry.usage ?? {}) as Record<string, unknown>;
  const failureKind = metadata.failure_kind ? String(metadata.failure_kind) : null;
  const intakeErrors = Array.isArray(metadata.intake_errors)
    ? metadata.intake_errors.map((x) => String(x))
    : [];

  const title = useMemo(() => {
    if (!content) return "Detalle de ejecución";
    return `${content.agent_type} · #${content.id}`;
  }, [content]);

  if (executionId == null) return null;

  return (
    <div className={styles.backdrop} onClick={(e) => e.currentTarget === e.target && onClose()}>
      <aside className={styles.drawer} role="dialog" aria-modal="true" aria-label="Detalle de ejecución">
        <header className={styles.header}>
          <div>
            <h3 className={styles.title}>{title}</h3>
            {content && (
              <div className={styles.subtitle}>
                Ticket {content.ticket_id} · {content.status} · {formatDuration(content.duration_ms)}
              </div>
            )}
          </div>
          <button className={styles.closeButton} onClick={onClose} title="Cerrar detalle">
            <X size={16} />
          </button>
        </header>

        {execQ.isLoading && <div className={styles.loading}>Cargando ejecución…</div>}
        {execQ.isError && <div className={styles.error}>No se pudo cargar la ejecución.</div>}

        {content && (
          <>
            {content.contract_result && (
              <section className={styles.section}>
                <ContractBadge result={content.contract_result} />
              </section>
            )}

            {/* Plan 117 — insight local (TL;DR + triage) */}
            <ExecutionInsightBlock
              executionId={executionId}
              insight={(metadata.local_insight ?? null) as ExecutionLocalInsight | null}
              onRegenerated={() => execQ.refetch()}
            />

            {/* Plan 127 C1 — análisis de error con IA local (forense, HITL) */}
            <ExecutionErrorAnalysisBlock
              executionId={executionId}
              status={content.status}
              metadata={metadata}
              onRegenerated={() => execQ.refetch()}
            />

            <section className={styles.section}>
              <h4>Telemetría</h4>
              <div className={styles.metrics}>
                <span>Costo: {formatMaybeCurrency(claudeTelemetry.total_cost_usd)}</span>
                <span>Input tokens: {formatTokens(usage.input_tokens)}</span>
                <span>Output tokens: {formatTokens(usage.output_tokens)}</span>
                <span>Turnos: {formatTokens(claudeTelemetry.num_turns)}</span>
              </div>
            </section>

            <section className={styles.section}>
              <h4>Artefactos</h4>
              {filesQ.isLoading && <div className={styles.loading}>Cargando artefactos…</div>}
              {!filesQ.isLoading && (filesQ.data?.files?.length ?? 0) === 0 && (
                <div className={styles.muted}>Sin artefactos registrados.</div>
              )}
              {(filesQ.data?.files ?? []).length > 0 && (
                <ul className={styles.fileList}>
                  {filesQ.data?.files.map((f) => {
                    const absolutePath = filesQ.data?.dir ? `${filesQ.data.dir}/${f.rel_path}` : f.rel_path;
                    return (
                      <li key={f.rel_path} className={styles.fileRow}>
                        <div>
                          <div className={styles.fileName}>{f.name}</div>
                          <div className={styles.fileMeta}>{f.rel_path} · {f.size} bytes</div>
                        </div>
                        <button
                          className={styles.copyButton}
                          title="Copiar ruta"
                          onClick={() => void navigator.clipboard.writeText(absolutePath)}
                        >
                          <Copy size={14} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {content.error_message && (
              <section className={styles.section}>
                <h4>Error</h4>
                {failureKind && <div className={styles.muted}>failure_kind: {failureKind}</div>}
                {intakeErrors.length > 0 && (
                  <ul className={styles.fileList}>
                    {intakeErrors.map((err) => (
                      <li key={err} className={styles.fileMeta}>{err}</li>
                    ))}
                  </ul>
                )}
                <pre className={styles.errorBlock}>{content.error_message}</pre>
              </section>
            )}

            {/* Plan 38 C2 — Sección Trazabilidad */}
            {(metadata.agent_name || metadata.prompt_sha || metadata.produced_files) && (
              <section className={styles.section}>
                <h4>Trazabilidad</h4>
                <div className={styles.trace}>
                  <div>
                    <span className={styles.muted}>Agente: </span>
                    <span>{metadata.agent_name ? String(metadata.agent_name) : "—"}</span>
                  </div>
                  <div>
                    <span className={styles.muted}>Prompt SHA: </span>
                    <code style={{ fontSize: 11, wordBreak: "break-all" }}>
                      {metadata.prompt_sha ? String(metadata.prompt_sha) : "—"}
                    </code>
                  </div>
                  {Boolean(metadata.prompt_text) && (
                    <details>
                      <summary className={styles.muted} style={{ cursor: "pointer", fontSize: 12 }}>
                        Prompt text (expandir)
                      </summary>
                      <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-all", marginTop: 4 }}>
                        {String(metadata.prompt_text ?? "")}
                      </pre>
                    </details>
                  )}
                  <div>
                    <span className={styles.muted}>Archivos producidos: </span>
                    {Array.isArray(metadata.produced_files) && (metadata.produced_files as string[]).length > 0 ? (
                      <ul style={{ margin: "4px 0 0 12px", padding: 0 }}>
                        {(metadata.produced_files as string[]).map((f) => (
                          <li key={f} style={{ fontSize: 12 }}>{f}</li>
                        ))}
                      </ul>
                    ) : (
                      <span>sin archivos registrados</span>
                    )}
                  </div>
                </div>
              </section>
            )}

            {/* Plan 42 F4 — Resumen post-épica (epic_summary en metadata) */}
            {metadata.epic_summary && typeof metadata.epic_summary === "object" && (() => {
              const s = metadata.epic_summary as Record<string, unknown>;
              return (
                <section className={styles.section}>
                  <h4>Resumen de Épica</h4>
                  <div className={styles.trace}>
                    {s.ado_id != null && (
                      <div>
                        <span className={styles.muted}>ADO ID: </span>
                        <strong>ADO-{String(s.ado_id)}</strong>
                        {typeof s.ado_url === "string" && s.ado_url && (
                          <> · <a href={s.ado_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>ver en ADO</a></>
                        )}
                      </div>
                    )}
                    <div>
                      <span className={styles.muted}>RFs: </span>
                      <span>{typeof s.rf_count === "number" ? s.rf_count : "—"}</span>
                    </div>
                    {Array.isArray(s.cited_modules) && (s.cited_modules as string[]).length > 0 && (
                      <div>
                        <span className={styles.muted}>Módulos/procesos citados: </span>
                        <span>{(s.cited_modules as string[]).join(", ")}</span>
                      </div>
                    )}
                    {Array.isArray(s.warnings) && (s.warnings as string[]).length > 0 && (
                      <div style={{ color: "var(--color-warning, #b45309)", fontSize: 12, marginTop: 4 }}>
                        {(s.warnings as string[]).map((w, i) => <div key={i}>{w}</div>)}
                      </div>
                    )}
                  </div>
                </section>
              );
            })()}

            <section className={styles.section}>
              <h4>Output</h4>
              {content.output ? (
                <StructuredOutput output={content.output} agentType={content.agent_type} />
              ) : (
                <div className={styles.muted}>Sin output guardado.</div>
              )}
            </section>
          </>
        )}
      </aside>
    </div>
  );
}

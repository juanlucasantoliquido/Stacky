import { Copy, Play, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { QaBrowser, Tickets } from "../api/endpoints";
import type { QaBrowserRunResponse } from "../api/endpoints";
import type { Ticket } from "../types";
import { useWorkbench } from "../store/workbench";
import styles from "./QaBrowserRunModal.module.css";

interface QaBrowserRunModalProps {
  ticket?: Ticket | null;
  onClose: () => void;
}

const DEFAULT_BASE_URL = "http://localhost:35017/AgendaWeb/";

export default function QaBrowserRunModal({ ticket, onClose }: QaBrowserRunModalProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Ticket | null>(ticket ?? null);
  const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem("stacky_qa_browser_base_url") || DEFAULT_BASE_URL);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<QaBrowserRunResponse | null>(null);
  const setCodexConsoleExecution = useWorkbench((state) => state.setCodexConsoleExecution);

  useEffect(() => {
    if (ticket) return;
    Tickets.list().then(setTickets).catch(() => setTickets([]));
  }, [ticket]);

  const filteredTickets = useMemo(() => {
    if (ticket) return [];
    const q = query.trim().toLowerCase();
    if (!q) return tickets.slice(0, 30);
    return tickets
      .filter(
        (t) =>
          String(t.ado_id).includes(q) ||
          t.title.toLowerCase().includes(q) ||
          (t.project ?? "").toLowerCase().includes(q)
      )
      .slice(0, 30);
  }, [query, ticket, tickets]);

  async function copyPrompt(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  async function handleStart() {
    if (!selected) return;
    setLoading(true);
    setError(null);
    try {
      localStorage.setItem("stacky_qa_browser_base_url", baseUrl);
      const response = await QaBrowser.startRun({
        ticket_id: selected.id,
        allowed_base_url: baseUrl,
        operator_note: note.trim() || undefined,
        max_scenarios: 16,
        auto_start: true,
      });
      setRun(response);
      setCodexConsoleExecution(response.execution_id, false);
      if (response.status === "queued") {
        await copyPrompt(response.runner_prompt);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  const selectedLabel = selected
    ? `ADO-${selected.ado_id} - ${selected.title}`
    : "Selecciona un ticket";
  const runStarted = run?.status === "running";

  return (
    <div className={styles.backdrop} onClick={(e) => e.currentTarget === e.target && onClose()}>
      <section className={styles.modal} role="dialog" aria-modal="true" aria-label="TEST QA UAT CODEX">
        <header className={styles.header}>
          <div>
            <h2>TEST QA UAT CODEX</h2>
            <p>{selectedLabel}</p>
          </div>
          <button className={styles.iconButton} onClick={onClose} title="Cerrar">
            <X size={16} />
          </button>
        </header>

        {!ticket && (
          <>
            <input
              className={styles.input}
              placeholder="Buscar ticket por ID, titulo o proyecto"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className={styles.ticketList}>
              {filteredTickets.map((t) => (
                <button
                  key={t.id}
                  className={selected?.id === t.id ? styles.ticketActive : styles.ticket}
                  onClick={() => setSelected(t)}
                >
                  <span>ADO-{t.ado_id}</span>
                  <strong>{t.title}</strong>
                  <em>{t.ado_state ?? "-"}</em>
                </button>
              ))}
            </div>
          </>
        )}

        <label className={styles.field}>
          <span>URL base permitida</span>
          <input
            className={styles.input}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={DEFAULT_BASE_URL}
          />
        </label>

        <label className={styles.field}>
          <span>Nota para el tester</span>
          <textarea
            className={styles.textarea}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Datos de prueba, usuario ya logueado, pantalla inicial esperada..."
          />
        </label>

        {error && <div className={styles.error}>{error}</div>}

        {run && (
          <div className={styles.result}>
            <div className={styles.resultTop}>
              <span>Run #{run.execution_id}</span>
              <span>{run.status === "queued" ? "preparado" : run.status}</span>
              <span>{run.spec.scenarios.length} escenarios</span>
              <span>{run.spec.plan_source.used_sources.length} fuentes</span>
            </div>
            <div className={styles.handoff}>
              <strong>{runStarted ? "Run iniciado." : "Run preparado."}</strong>
              <span>
                {runStarted
                  ? "Stacky ya trajo descripcion, comentarios y adjuntos del ticket, inicio Codex y abrio la consola para seguir la ejecucion. El prompt queda disponible abajo como respaldo operativo."
                  : "Stacky ya trajo descripcion, comentarios y adjuntos del ticket. El prompt quedo copiado: pegalo en Codex para que el navegador visible ejecute el plan y cierre el run publicando el comentario en ADO."}
              </span>
            </div>
            <div className={styles.sourceList}>
              {run.spec.plan_source.used_sources.length === 0 ? (
                <span>Sin fuente de plan detectable</span>
              ) : (
                run.spec.plan_source.used_sources.map((src) => (
                  <span key={`${src.kind}-${src.source_id}`}>{src.title}</span>
                ))
              )}
            </div>
            <textarea className={styles.prompt} readOnly value={run.runner_prompt} />
          </div>
        )}

        <footer className={styles.actions}>
          {run && (
            <button className={styles.secondaryBtn} onClick={() => copyPrompt(run.runner_prompt)}>
              <Copy size={14} />
              {copyState === "copied" ? "Prompt copiado" : copyState === "failed" ? "No se pudo copiar" : "Copiar prompt"}
            </button>
          )}
          <button className={styles.cancelBtn} onClick={onClose}>
            Cerrar
          </button>
          <button className={styles.primaryBtn} onClick={handleStart} disabled={!selected || loading}>
            <Play size={14} />
            {loading ? "Preparando..." : "TEST QA UAT CODEX"}
          </button>
        </footer>
      </section>
    </div>
  );
}

/**
 * TicketLocalInsightButton — "Estado con IA local" en la card de un ticket.
 *
 * Un click → POST /api/llm/ticket-insight/{ticketId}: el backend reúne TODO el
 * contexto (épica padre, tasks hijas, comentarios del tracker y outputs de los
 * agentes) y el modelo local devuelve resumen de estado, puntos débiles e
 * incoherencias entre agentes. HITL puro: solo analiza, no toca nada.
 *
 * Si la flag LOCAL_LLM_ENABLED está OFF el backend responde 404 y el botón
 * muestra el aviso de "apagado" (patrón LocalLlmPlaygroundPanel), sin crashear.
 */
import { useCallback, useState } from "react";
import { LocalLlmApi } from "../api/endpoints";
import styles from "./TicketLocalInsightButton.module.css";

interface Props {
  ticketId: number;
}

interface InsightResult {
  analysis: string;
  model: string;
  contextStats: { has_epic: boolean; children: number; comments: number; executions: number };
}

export default function TicketLocalInsightButton({ ticketId }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InsightResult | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const handleAnalyze = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await LocalLlmApi.ticketInsight(ticketId);
      setResult({
        analysis: res.analysis ?? "",
        model: res.model ?? "",
        contextStats: res.context_stats,
      });
      setCollapsed(false);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error desconocido";
      if (msg.includes("local_llm_disabled") || msg.startsWith("404")) {
        setError(
          "La IA local está apagada. Activá la flag «Modelo local (Ollama/LM Studio/vLLM)» en la pestaña Arnés.",
        );
      } else {
        setError(`El modelo local no pudo analizar el ticket: ${msg}`);
      }
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  return (
    <div className={styles.wrap} onClick={(e) => e.stopPropagation()}>
      <button
        className={styles.btn}
        onClick={() => void handleAnalyze()}
        disabled={loading}
        title="Analiza estado, puntos débiles e incoherencias con tu modelo local (gratis, sin salir de tu máquina)"
      >
        {loading ? "⏳ Analizando con IA local…" : "🧠 Estado con IA local"}
      </button>

      {error && <div className={styles.error}>{error}</div>}

      {result && (
        <div className={styles.result}>
          <div className={styles.resultHead}>
            <span>
              Análisis local · {result.model}
              {result.contextStats && (
                <span className={styles.stats}>
                  {" "}
                  · {result.contextStats.executions} run(s) · {result.contextStats.comments}{" "}
                  comentario(s) · {result.contextStats.children} hija(s)
                  {result.contextStats.has_epic ? " · con épica" : ""}
                </span>
              )}
            </span>
            <span className={styles.headActions}>
              <button className={styles.linkBtn} onClick={() => setCollapsed((c) => !c)}>
                {collapsed ? "Expandir" : "Colapsar"}
              </button>
              <button className={styles.linkBtn} onClick={() => setResult(null)}>
                Cerrar
              </button>
            </span>
          </div>
          {!collapsed && <pre className={styles.resultBody}>{result.analysis || "(respuesta vacía)"}</pre>}
        </div>
      )}
    </div>
  );
}

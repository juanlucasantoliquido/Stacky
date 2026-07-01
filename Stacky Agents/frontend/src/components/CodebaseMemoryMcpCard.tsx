/**
 * Plan 80 F6 — Card read-only de estado del MCP externo codebase-memory-mcp.
 *
 * Muestra: enabled, binary_path_set, injects_external, y el ahorro estimado
 * (samples/delta_pct de /savings, "sin datos aún" si delta_pct es null).
 * SIN toggle: el toggle del flag lo renderiza HarnessFlagsPanel.
 */

import { useQuery } from "@tanstack/react-query";
import { CodebaseMemoryMcp } from "../api/endpoints";
import styles from "./CodebaseMemoryMcpCard.module.css";

export default function CodebaseMemoryMcpCard() {
  const statusQ = useQuery({
    queryKey: ["codebase-memory-mcp-status"],
    queryFn: () => CodebaseMemoryMcp.status(),
    retry: 1,
  });

  const savingsQ = useQuery({
    queryKey: ["codebase-memory-mcp-savings"],
    queryFn: () => CodebaseMemoryMcp.savings(),
    retry: 1,
    enabled: !!statusQ.data,
  });

  if (statusQ.isLoading) {
    return (
      <div className={styles.card}>
        <p className={styles.loading}>Cargando estado de Codebase Memory MCP…</p>
      </div>
    );
  }

  if (statusQ.isError || !statusQ.data) {
    return (
      <div className={styles.card}>
        <p className={styles.errorMsg}>No se pudo cargar el estado de Codebase Memory MCP.</p>
      </div>
    );
  }

  const st = statusQ.data;
  const savings = savingsQ.data;
  const savingsLabel =
    savings && savings.delta_pct != null
      ? `${(savings.delta_pct * 100).toFixed(1)}% (n=${savings.samples})`
      : "sin datos aún";

  return (
    <div className={styles.card}>
      <h2 className={styles.title}>Codebase Memory MCP (externo)</h2>
      <div className={styles.metricsGrid}>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Flag activo</span>
          <span className={styles.metricValue}>{st.enabled ? "Sí" : "No"}</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Ruta del binario configurada</span>
          <span className={styles.metricValue}>{st.wiring.binary_path_set ? "Sí" : "No"}</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Inyecta 2º server (Claude CLI)</span>
          <span className={styles.metricValue}>{st.wiring.injects_external ? "Sí" : "No"}</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Ahorro estimado</span>
          <span className={styles.metricValue}>{savingsLabel}</span>
        </div>
      </div>
      <p className={styles.link}>
        Configurar en HarnessFlagsPanel (categoría &quot;Avanzado / experimental&quot;). Guía de
        instalación: ver <code>docs/_evals/codebase-memory-mcp/</code>.
      </p>
    </div>
  );
}

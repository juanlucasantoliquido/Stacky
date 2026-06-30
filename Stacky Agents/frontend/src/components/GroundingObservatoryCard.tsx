/**
 * Plan 44 F4 — Observatorio pasivo de grounding de épicas.
 *
 * Card solo-lectura que muestra métricas de grounding de épicas:
 * - Total de épicas, tasa de warnings, confianza promedio
 * - Cobertura por runtime (nota si faltan codex_cli o github_copilot)
 * - Sparkline de confianza
 * - Top módulos/procesos citados
 * - Sección "Procesos sugeridos" con form inline para agregar al diccionario
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Agents, ClientProfileApi, type GroundingObservatoryResponse } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./GroundingObservatoryCard.module.css";

// ── Tipos ────────────────────────────────────────────────────────────────────

interface AddingProcess {
  name: string;
  purpose: string;
  kind: "entry" | "processing" | "output";
}

// ── Sub-componentes ──────────────────────────────────────────────────────────

function SparklineBar({ value }: { value: number | null }) {
  const h = value == null ? 0 : Math.max(4, value * 100);
  return <div className={styles.sparklineBar} style={{ height: `${h}%` }} />;
}

function Sparkline({ data }: { data: (number | null)[] }) {
  if (data.length === 0) return <p className={styles.empty}>Sin datos de tendencia.</p>;
  return (
    <div className={styles.sparklineContainer}>
      {data.map((v, i) => (
        <SparklineBar key={i} value={v} />
      ))}
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────

export default function GroundingObservatoryCard() {
  const activeProject = useWorkbench((s) => s.activeProject);
  const [addingProcess, setAddingProcess] = useState<AddingProcess | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const groundingQ = useQuery({
    queryKey: ["grounding-observatory", activeProject?.name],
    queryFn: () => Agents.groundingObservatory(activeProject?.name),
    enabled: !!activeProject?.name,
    retry: 1,
  });

  const suggestionsQ = useQuery({
    queryKey: ["process-catalog-suggestions", activeProject?.name],
    queryFn: () => Agents.processCatalogSuggestions(activeProject!.name),
    enabled: !!activeProject?.name,
    retry: 1,
  });

  const clientProfileQ = useQuery({
    queryKey: ["client-profile", activeProject?.name],
    queryFn: () => ClientProfileApi.get(activeProject!.name),
    enabled: false, // Manual trigger only
  });

  async function handleAddProcess(suggestion: { name: string; occurrences: number }) {
    setAddingProcess({
      name: suggestion.name,
      purpose: "",
      kind: "processing",
    });
    setAddError(null);
  }

  async function handleConfirmAdd() {
    if (!addingProcess || !activeProject?.name) return;

    setAdding(true);
    setAddError(null);

    try {
      // 1. Obtener el client-profile actual
      const profileRes = await ClientProfileApi.get(activeProject.name);
      if (!profileRes.ok || !profileRes.profile) {
        throw new Error(profileRes.error || "No se pudo cargar el perfil.");
      }

      // 2. Agregar la entrada al process_catalog
      const updated = { ...profileRes.profile };
      if (!updated.process_catalog) {
        updated.process_catalog = [];
      }
      (updated.process_catalog as Array<any>).push({
        name: addingProcess.name,
        kind: addingProcess.kind,
        purpose: addingProcess.purpose,
      });

      // 3. Guardar el perfil actualizado
      const saveRes = await ClientProfileApi.save(activeProject.name, updated);
      if (!saveRes.ok) {
        throw new Error(saveRes.error || "No se pudo guardar el perfil.");
      }

      // 4. Refrescar sugerencias
      setAddingProcess(null);
      suggestionsQ.refetch();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setAdding(false);
    }
  }

  // Si el endpoint devuelve 404 (flag OFF), no mostrar nada
  if (groundingQ.isError && (groundingQ.error as any)?.status === 404) {
    return null;
  }

  // Mientras carga
  if (groundingQ.isLoading) {
    return (
      <div className={styles.card}>
        <p className={styles.loading}>Cargando observatorio de grounding…</p>
      </div>
    );
  }

  // Si hay error
  if (groundingQ.isError || !groundingQ.data) {
    return (
      <div className={`${styles.card} ${styles.cardError}`}>
        <p className={styles.errorMsg}>No se pudo cargar el observatorio de grounding.</p>
      </div>
    );
  }

  const data: GroundingObservatoryResponse = groundingQ.data;

  // Si no hay épicas, mostrar mensaje
  if (data.total_epics === 0) {
    return (
      <div className={styles.card}>
        <h2 className={styles.title}>Observatorio de grounding</h2>
        <p className={styles.empty}>Aún no hay épicas para analizar.</p>
      </div>
    );
  }

  // Verificar cobertura de runtime
  const missingRuntimes: string[] = [];
  if (!data.runtime_coverage.includes("codex_cli")) missingRuntimes.push("Codex");
  if (!data.runtime_coverage.includes("github_copilot")) missingRuntimes.push("Copilot");

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Observatorio de grounding</h2>
      </div>

      {/* Métricas principales */}
      <div className={styles.metricsGrid}>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Total de épicas</span>
          <span className={styles.metricValue}>{data.total_epics}</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Épicas con warnings</span>
          <span className={styles.metricValue}>{data.epics_with_warnings}</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Tasa de warnings</span>
          <span className={styles.metricValue}>{(data.grounding_warning_rate * 100).toFixed(1)}%</span>
        </div>
        <div className={styles.metricBox}>
          <span className={styles.metricLabel}>Confianza promedio</span>
          <span className={styles.metricValue}>
            {data.avg_confidence != null ? `${(data.avg_confidence * 100).toFixed(1)}%` : "—"}
          </span>
        </div>
      </div>

      {/* Nota de cobertura parcial */}
      {missingRuntimes.length > 0 && data.runtime_coverage.length > 0 && (
        <div className={styles.coverageNote}>
          <span>⚠ Cobertura parcial: {data.runtime_coverage.join(", ")} — {missingRuntimes.join("/")} aún sin epic_summary.</span>
        </div>
      )}

      {/* Tendencia de confianza */}
      <div className={styles.trendSection}>
        <h3 className={styles.sectionTitle}>Tendencia de confianza</h3>
        <Sparkline data={data.confidence_trend} />
      </div>

      {/* Top módulos citados */}
      {data.top_cited_modules.length > 0 && (
        <div className={styles.listSection}>
          <h3 className={styles.sectionTitle}>Top módulos citados</h3>
          <ul className={styles.list}>
            {data.top_cited_modules.map((m) => (
              <li key={m.name}>
                <span className={styles.listName}>{m.name}</span>
                <span className={styles.listCount}>{m.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Top procesos citados */}
      {data.top_cited_processes.length > 0 && (
        <div className={styles.listSection}>
          <h3 className={styles.sectionTitle}>Top procesos citados</h3>
          <ul className={styles.list}>
            {data.top_cited_processes.map((p) => (
              <li key={p.name}>
                <span className={styles.listName}>{p.name}</span>
                <span className={styles.listCount}>{p.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Procesos sugeridos */}
      {suggestionsQ.data && suggestionsQ.data.suggestions.length > 0 && (
        <div className={styles.suggestionsSection}>
          <h3 className={styles.sectionTitle}>Procesos sugeridos para el diccionario</h3>
          {addingProcess ? (
            <div className={styles.formInline}>
              <div className={styles.formField}>
                <label className={styles.formLabel}>Proceso: {addingProcess.name}</label>
              </div>
              <div className={styles.formField}>
                <label className={styles.formLabel}>Tipo *</label>
                <select
                  className={styles.formSelect}
                  value={addingProcess.kind}
                  onChange={(e) =>
                    setAddingProcess({ ...addingProcess, kind: e.target.value as any })
                  }
                >
                  <option value="entry">Entry (entrada)</option>
                  <option value="processing">Processing (procesamiento)</option>
                  <option value="output">Output (salida)</option>
                </select>
              </div>
              <div className={styles.formField}>
                <label className={styles.formLabel}>Propósito</label>
                <input
                  type="text"
                  className={styles.formInput}
                  placeholder="Descripción breve"
                  value={addingProcess.purpose}
                  onChange={(e) =>
                    setAddingProcess({ ...addingProcess, purpose: e.target.value })
                  }
                />
              </div>
              {addError && <p className={styles.formError}>{addError}</p>}
              <div className={styles.formActions}>
                <button
                  className={styles.btnConfirm}
                  disabled={adding}
                  onClick={handleConfirmAdd}
                >
                  {adding ? "Guardando…" : "Guardar"}
                </button>
                <button
                  className={styles.btnCancel}
                  disabled={adding}
                  onClick={() => {
                    setAddingProcess(null);
                    setAddError(null);
                  }}
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <ul className={styles.suggestionsList}>
              {suggestionsQ.data.suggestions.map((s) => (
                <li key={s.name} className={styles.suggestionItem}>
                  <span className={styles.suggestionName}>{s.name}</span>
                  <span className={styles.suggestionCount}>{s.occurrences}</span>
                  <button
                    className={styles.btnAdd}
                    onClick={() => handleAddProcess(s)}
                  >
                    Agregar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

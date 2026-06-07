import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Memory,
  type StackyMemoryFinding,
  type StackyMemoryFindingAction,
  type StackyMemoryObservation,
  type StackyMemoryStatus,
} from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { MEMORY_ADVANCED_ENABLED } from "../config/featureFlags";
import styles from "./MemoryPage.module.css";

type Tab = "memories" | "drafts" | "triage" | "graph";

const STATUS_LABELS: Record<string, string> = {
  active: "Activa",
  draft: "Draft",
  needs_review: "Review",
  superseded: "Superseded",
  quarantined: "Cuarentena",
  rejected: "Rechazada",
};

const FINDING_ACTIONS: { action: StackyMemoryFindingAction; label: string; needsPair?: boolean }[] = [
  { action: "activate_memory", label: "Activar" },
  { action: "needs_review_memory", label: "Review" },
  { action: "quarantine_memory", label: "Cuarentena" },
  { action: "mark_supersedes", label: "Supersede", needsPair: true },
  { action: "mark_duplicates", label: "Duplicado", needsPair: true },
  { action: "mark_conflicts_with", label: "Conflicto", needsPair: true },
  { action: "mark_not_conflict", label: "No conflicto", needsPair: true },
];

function memoryIds(finding: StackyMemoryFinding): string[] {
  const fromEvidence = Array.isArray(finding.evidence?.memory_ids)
    ? finding.evidence.memory_ids.filter((x: unknown): x is string => typeof x === "string")
    : [];
  if (finding.memory_id && !fromEvidence.includes(finding.memory_id)) {
    return [finding.memory_id, ...fromEvidence];
  }
  return fromEvidence;
}

function MemoryRow({
  row,
  onStatus,
}: {
  row: StackyMemoryObservation;
  onStatus: (id: string, status: StackyMemoryStatus) => void;
}) {
  return (
    <article className={styles.memoryRow}>
      <div className={styles.rowHeader}>
        <div className={styles.rowTitleBlock}>
          <div className={styles.rowTitle}>{row.title}</div>
          <div className={styles.rowMeta}>
            {row.type} · {row.scope}
            {row.topic_key ? ` · ${row.topic_key}` : ""}
            {row.source_ado_id ? ` · ADO-${row.source_ado_id}` : ""}
          </div>
        </div>
        <span className={`${styles.statusPill} ${styles[`status_${row.status}`] ?? ""}`}>
          {STATUS_LABELS[row.status] ?? row.status}
        </span>
      </div>
      <p className={styles.content}>{row.content}</p>
      <div className={styles.rowFooter}>
        <span>{row.memory_id}</span>
        <div className={styles.inlineActions}>
          <button onClick={() => onStatus(row.memory_id, "active")} disabled={row.status === "active"}>
            Activar
          </button>
          <button onClick={() => onStatus(row.memory_id, "needs_review")} disabled={row.status === "needs_review"}>
            Review
          </button>
          <button onClick={() => onStatus(row.memory_id, "quarantined")} disabled={row.status === "quarantined"}>
            Cuarentena
          </button>
        </div>
      </div>
    </article>
  );
}

function FindingRow({
  finding,
  onAction,
  busy,
}: {
  finding: StackyMemoryFinding;
  onAction: (finding: StackyMemoryFinding, action: StackyMemoryFindingAction) => void;
  busy: boolean;
}) {
  const ids = memoryIds(finding);
  return (
    <article className={styles.findingRow}>
      <div className={styles.rowHeader}>
        <div className={styles.rowTitleBlock}>
          <div className={styles.rowTitle}>{finding.title}</div>
          <div className={styles.rowMeta}>
            {finding.check_name} · {finding.severity}
            {ids.length ? ` · ${ids.join(" / ")}` : ""}
          </div>
        </div>
        <span className={`${styles.severity} ${styles[`sev_${finding.severity}`] ?? ""}`}>
          {finding.severity}
        </span>
      </div>
      {finding.detail && <p className={styles.content}>{finding.detail}</p>}
      <div className={styles.actionGrid}>
        {FINDING_ACTIONS.map((item) => (
          <button
            key={item.action}
            onClick={() => onAction(finding, item.action)}
            disabled={busy || (item.needsPair && ids.length < 2)}
            title={item.needsPair && ids.length < 2 ? "Requiere dos memorias" : item.label}
          >
            {item.label}
          </button>
        ))}
      </div>
    </article>
  );
}

export default function MemoryPage() {
  const qc = useQueryClient();
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const [tab, setTab] = useState<Tab>("memories");
  const [status, setStatus] = useState<StackyMemoryStatus | "">("active");

  const project = activeProjectName ?? "";
  const memories = useQuery({
    queryKey: ["memory-list", project, status],
    queryFn: () => Memory.list({ project, status: status || undefined, limit: 300 }),
    enabled: !!project,
  });
  const drafts = useQuery({
    queryKey: ["memory-drafts", project],
    queryFn: () => Memory.list({ project, status: "draft", limit: 100 }),
    enabled: !!project,
  });
  const findings = useQuery({
    queryKey: ["memory-findings", project],
    queryFn: () => Memory.findings({ project, status: "open", limit: 200 }),
    enabled: !!project,
  });
  const graph = useQuery({
    queryKey: ["memory-conflict-graph", project],
    queryFn: () => Memory.conflictGraph(project),
    enabled: !!project && tab === "graph",
  });
  const runs = useQuery({
    queryKey: ["memory-validation-runs", project],
    queryFn: () => Memory.validationRuns(project, 10),
    enabled: !!project,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["memory-list", project] });
    qc.invalidateQueries({ queryKey: ["memory-drafts", project] });
    qc.invalidateQueries({ queryKey: ["memory-findings", project] });
    qc.invalidateQueries({ queryKey: ["memory-conflict-graph", project] });
    qc.invalidateQueries({ queryKey: ["memory-validation-runs", project] });
    qc.invalidateQueries({ queryKey: ["memory-ticket-badges", project] });
  };

  const statusMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: StackyMemoryStatus }) => Memory.setStatus(id, next),
    onSuccess: refresh,
  });
  const validationMutation = useMutation({
    // Sin `checks`: el backend corre los 4 baratos por default; los avanzados
    // exigen STACKY_MEMORY_VALIDATOR_ADVANCED en el server (no se fuerzan acá).
    mutationFn: () => Memory.startValidation({ project }),
    onSuccess: refresh,
  });
  const findingMutation = useMutation({
    mutationFn: ({ finding, action }: { finding: StackyMemoryFinding; action: StackyMemoryFindingAction }) => {
      const ids = memoryIds(finding);
      return Memory.applyFindingAction(finding.id, {
        action,
        source_memory_id: ids[0] ?? finding.memory_id,
        target_memory_id: ids[1] ?? null,
        reason: `${action} desde MemoryPage`,
      });
    },
    onSuccess: refresh,
  });

  const latestRun = runs.data?.[0];
  const openFindings = findings.data ?? [];
  const groupedFindings = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of openFindings) map.set(f.check_name, (map.get(f.check_name) ?? 0) + 1);
    return Array.from(map.entries());
  }, [openFindings]);

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <h1>Memoria Stacky</h1>
          <p>{project || "Sin proyecto activo"}</p>
        </div>
        {MEMORY_ADVANCED_ENABLED && (
          <div className={styles.headerActions}>
            {latestRun && (
              <span className={styles.runPill}>
                Run #{latestRun.id} · {latestRun.status}
              </span>
            )}
            <button
              className={styles.primaryBtn}
              onClick={() => validationMutation.mutate()}
              disabled={!project || validationMutation.isPending}
            >
              {validationMutation.isPending ? "Validando" : "Validar"}
            </button>
          </div>
        )}
      </header>

      <nav className={styles.tabs}>
        <button className={tab === "memories" ? styles.activeTab : ""} onClick={() => setTab("memories")}>
          Memorias
        </button>
        <button className={tab === "drafts" ? styles.activeTab : ""} onClick={() => setTab("drafts")}>
          Borradores {drafts.data?.length ? `(${drafts.data.length})` : ""}
        </button>
        {MEMORY_ADVANCED_ENABLED && (
          <>
            <button className={tab === "triage" ? styles.activeTab : ""} onClick={() => setTab("triage")}>
              Triage {openFindings.length ? `(${openFindings.length})` : ""}
            </button>
            <button className={tab === "graph" ? styles.activeTab : ""} onClick={() => setTab("graph")}>
              Grafo
            </button>
          </>
        )}
      </nav>

      {!project && <div className={styles.empty}>Selecciona un proyecto para ver memoria colaborativa.</div>}

      {project && tab === "memories" && (
        <main className={styles.main}>
          <div className={styles.toolbar}>
            <select value={status} onChange={(e) => setStatus(e.target.value as StackyMemoryStatus | "")}>
              <option value="">Todos</option>
              <option value="active">Activas</option>
              <option value="draft">Drafts</option>
              <option value="needs_review">Review</option>
              <option value="quarantined">Cuarentena</option>
              <option value="superseded">Superseded</option>
            </select>
            <span>{memories.data?.length ?? 0} items</span>
          </div>
          {memories.isLoading && <div className={styles.empty}>Cargando memoria...</div>}
          {(memories.data ?? []).map((row) => (
            <MemoryRow
              key={row.memory_id}
              row={row}
              onStatus={(id, next) => statusMutation.mutate({ id, next })}
            />
          ))}
        </main>
      )}

      {project && tab === "drafts" && (
        <main className={styles.main}>
          <div className={styles.toolbar}>
            <span>{drafts.data?.length ?? 0} borradores pendientes de promover</span>
          </div>
          {drafts.isLoading && <div className={styles.empty}>Cargando borradores...</div>}
          {!drafts.isLoading && (drafts.data ?? []).length === 0 && (
            <div className={styles.empty}>
              No hay borradores. Se crean automáticamente al completar ejecuciones (captura post-run). Usá “Activar” para promoverlos.
            </div>
          )}
          {(drafts.data ?? []).map((row) => (
            <MemoryRow
              key={row.memory_id}
              row={row}
              onStatus={(id, next) => statusMutation.mutate({ id, next })}
            />
          ))}
        </main>
      )}

      {project && MEMORY_ADVANCED_ENABLED && tab === "triage" && (
        <main className={styles.main}>
          <section className={styles.summaryBand}>
            <span>{drafts.data?.length ?? 0} drafts</span>
            {groupedFindings.map(([check, count]) => (
              <span key={check}>{check}: {count}</span>
            ))}
          </section>
          {openFindings.length === 0 && <div className={styles.empty}>No hay hallazgos abiertos.</div>}
          {openFindings.map((finding) => (
            <FindingRow
              key={finding.id}
              finding={finding}
              busy={findingMutation.isPending}
              onAction={(f, action) => findingMutation.mutate({ finding: f, action })}
            />
          ))}
        </main>
      )}

      {project && MEMORY_ADVANCED_ENABLED && tab === "graph" && (
        <main className={styles.main}>
          {graph.isLoading && <div className={styles.empty}>Cargando grafo...</div>}
          {graph.data && graph.data.edges.length === 0 && (
            <div className={styles.empty}>No hay conflictos abiertos.</div>
          )}
          {graph.data && graph.data.edges.length > 0 && (
            <div className={styles.graphGrid}>
              {graph.data.edges.map((edge) => {
                const source = graph.data.nodes.find((n) => n.memory_id === edge.source_memory_id);
                const target = graph.data.nodes.find((n) => n.memory_id === edge.target_memory_id);
                return (
                  <article key={edge.relation_id} className={styles.graphEdge}>
                    <div className={styles.graphNode}>
                      <strong>{source?.title ?? edge.source_memory_id}</strong>
                      <span>{source?.type ?? "memory"}</span>
                    </div>
                    <div className={styles.graphRelation}>conflicts_with</div>
                    <div className={styles.graphNode}>
                      <strong>{target?.title ?? edge.target_memory_id}</strong>
                      <span>{target?.type ?? "memory"}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </main>
      )}
    </div>
  );
}

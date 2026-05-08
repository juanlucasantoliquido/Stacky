import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { VsCodeAgent, AgentExecution, Ticket } from "../types";
import { Agents, Projects, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { useRunningStatus } from "../hooks/useRunningStatus";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import styles from "./TeamScreen.module.css";

export default function TeamScreen() {
  const [allAgents, setAllAgents] = useState<VsCodeAgent[]>([]);
  const [manageOpen, setManageOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // ─── Fuente de verdad: store, no localStorage ──────────────────────────────
  const activeProject = useWorkbench((s) => s.activeProject);
  const pinned = useWorkbench((s) => s.pinnedAgents);
  const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
  const teamLoading = useWorkbench((s) => s.teamLoading);
  const getAgentsError = useWorkbench((s) => s.getAgentsError);
  const [removeError, setRemoveError] = useState<string | null>(null);

  /** Quita un empleado del proyecto activo vía API y actualiza el store. */
  async function handleRemoveEmployee(filename: string) {
    if (!activeProject) return;
    const nextPinned = pinned.filter((f) => f !== filename);
    setRemoveError(null);
    try {
      await Projects.putAgents(activeProject.name, nextPinned);
      setPinnedAgents(nextPinned);
    } catch {
      setRemoveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
    }
  }

  // Running status — quién está trabajando ahora
  const { runningByTicket } = useRunningStatus();
  const { data: tickets } = useQuery<Ticket[]>({
    queryKey: ["tickets"],
    queryFn: Tickets.list,
    staleTime: 60_000,
  });
  const ticketById = useMemo<Map<number, Ticket>>(
    () => new Map((tickets ?? []).map((t) => [t.id, t])),
    [tickets]
  );
  // Map: inferred agent type → running execution (first match)
  const runningByAgentType = useMemo<Map<string, AgentExecution>>(() => {
    const map = new Map<string, AgentExecution>();
    for (const exec of runningByTicket.values()) {
      if (!map.has(exec.agent_type)) map.set(exec.agent_type, exec);
    }
    return map;
  }, [runningByTicket]);

  useEffect(() => {
    Agents.vsCodeAgents()
      .then(setAllAgents)
      .catch(() => setAllAgents([]))
      .finally(() => setLoading(false));
  }, []);

  function agentByFilename(filename: string): VsCodeAgent | undefined {
    return allAgents.find((a) => a.filename === filename);
  }

  function inferAgentType(filename: string): string {
    const f = filename.toLowerCase();
    if (f.includes("business") || f.includes("negocio")) return "business";
    if (f.includes("functional") || f.includes("funcional")) return "functional";
    if (f.includes("technical") || f.includes("tecnic")) return "technical";
    if (f.includes("dev") || f.includes("desarrollador")) return "developer";
    if (f.includes("qa") || f.includes("test")) return "qa";
    return "custom";
  }

  return (
    <div className={styles.root}>
      {/* ─── Header ─── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>⚡</span>
          <h1 className={styles.title}>Tu Equipo</h1>
          {pinned.length > 0 && (
            <span className={styles.count}>{pinned.length} agente{pinned.length !== 1 ? "s" : ""}</span>
          )}
        </div>
        <div className={styles.headerActions}>
          <button
            className={styles.addBtn}
            onClick={() => setManageOpen(true)}
            disabled={!activeProject}
            title={!activeProject ? "Seleccioná un proyecto primero" : undefined}
          >
            + Agregar empleado
          </button>
        </div>
      </header>

      {/* ─── Grid ─── */}
      <main className={styles.main}>
        {removeError && (
          <div className={styles.errorBanner} role="alert">
            ⚠ {removeError}
          </div>
        )}
        {getAgentsError && (
          <div className={styles.errorBanner} role="alert">
            ⚠ {getAgentsError}
          </div>
        )}
        {loading || teamLoading ? (
          <div className={styles.loadingGrid}>
            {[...Array(4)].map((_, i) => (
              <div key={i} className={styles.skeletonCard} aria-hidden="true" />
            ))}
          </div>
        ) : !activeProject ? (
          <NoProjectState />
        ) : pinned.length === 0 ? (
          <EmptyState onAdd={() => setManageOpen(true)} />
        ) : (
          <div className={styles.grid}>
            {pinned.map((filename) => {
              const agentType = inferAgentType(filename);
              const runningExec = runningByAgentType.get(agentType) ?? null;
              const runningAdoId = runningExec
                ? (ticketById.get(runningExec.ticket_id)?.ado_id ?? null)
                : null;
              return (
                <EmployeeCard
                  key={filename}
                  filename={filename}
                  agent={agentByFilename(filename)}
                  runningExecution={runningExec}
                  runningTicketAdoId={runningAdoId}
                  onEdit={(f) => setEditTarget(f)}
                  onRemoved={() => handleRemoveEmployee(filename)}
                />
              );
            })}
          </div>
        )}
      </main>

      {/* ─── Drawers ─── */}
      {manageOpen && (
        <TeamManageDrawer
          allAgents={allAgents}
          onClose={() => setManageOpen(false)}
        />
      )}

      {editTarget && (
        <EmployeeEditDrawer
          filename={editTarget}
          agent={agentByFilename(editTarget)}
          onClose={() => setEditTarget(null)}
          onRemoved={() => { setEditTarget(null); handleRemoveEmployee(editTarget); }}
        />
      )}
    </div>
  );
}

function NoProjectState() {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>📂</div>
      <h2 className={styles.emptyTitle}>Ningún proyecto activo</h2>
      <p className={styles.emptyText}>
        Seleccioná un proyecto desde la barra superior para ver su equipo.
      </p>
    </div>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>👥</div>
      <h2 className={styles.emptyTitle}>Tu equipo está vacío</h2>
      <p className={styles.emptyText}>
        Agregá tu primer agente para empezar a asignar tickets desde aquí.
      </p>
      <button className={styles.emptyBtn} onClick={onAdd}>
        + Agregar primer agente
      </button>
    </div>
  );
}

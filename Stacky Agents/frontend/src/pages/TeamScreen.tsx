import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { VsCodeAgent, AgentExecution, Ticket } from "../types";
import { Agents, Projects, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { useRunningStatus } from "../hooks/useRunningStatus";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import ResumeCard from "../components/ResumeCard";
import SavingsCard from "../components/SavingsCard";
import SharedEmptyState from "../components/EmptyState";
import { Skeleton } from "../components/ui";
import styles from "./TeamScreen.module.css";

export default function TeamScreen() {
  const [allAgents, setAllAgents] = useState<VsCodeAgent[]>([]);
  const [manageOpen, setManageOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // ─── Fuente de verdad: store, no localStorage ──────────────────────────────
  const activeProject = useWorkbench((s) => s.activeProject);
  const activeProjectName = activeProject?.name ?? null;
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
    queryKey: ["tickets", activeProjectName],
    queryFn: () => Tickets.list(activeProjectName),
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
    let cancelled = false;
    setLoading(true);
    Agents.vsCodeAgents()
      .then((agents) => {
        if (!cancelled) setAllAgents(agents);
      })
      .catch(() => {
        if (!cancelled) setAllAgents([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProjectName, manageOpen]);

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

      {/* ─── Adoption widgets: Resume + Savings ─── */}
      <ResumeCard
        projectName={activeProjectName}
        onResume={(ticketId) => {
          window.history.pushState({}, "", `/tickets?ticket=${ticketId}`);
          window.dispatchEvent(new PopStateEvent("popstate"));
        }}
      />
      <SavingsCard />

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
              <Skeleton key={i} height={120} radius="var(--radius-lg)" />
            ))}
          </div>
        ) : !activeProject ? (
          <SharedEmptyState variant="no_project" />
        ) : pinned.length === 0 ? (
          <SharedEmptyState variant="agents" actionLabel="Agregar agente" onAction={() => setManageOpen(true)} />
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


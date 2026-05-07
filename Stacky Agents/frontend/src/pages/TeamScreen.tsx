import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { VsCodeAgent, AgentExecution, Ticket } from "../types";
import { Agents, Tickets } from "../api/endpoints";
import { getPinnedAgents } from "../services/preferences";
import { useRunningStatus } from "../hooks/useRunningStatus";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import styles from "./TeamScreen.module.css";

export default function TeamScreen() {
  const [allAgents, setAllAgents] = useState<VsCodeAgent[]>([]);
  const [pinned, setPinned] = useState<string[]>(getPinnedAgents());
  const [manageOpen, setManageOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setPinned([...getPinnedAgents()]);
  }, []);

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
          <button className={styles.addBtn} onClick={() => setManageOpen(true)}>
            + Agregar empleado
          </button>
        </div>
      </header>

      {/* ─── Grid ─── */}
      <main className={styles.main}>
        {loading ? (
          <div className={styles.loading}>Cargando agentes…</div>
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
                  onRemoved={refresh}
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
          onClose={() => { setManageOpen(false); refresh(); }}
        />
      )}

      {editTarget && (
        <EmployeeEditDrawer
          filename={editTarget}
          agent={agentByFilename(editTarget)}
          onClose={() => { setEditTarget(null); refresh(); }}
          onRemoved={() => { setEditTarget(null); refresh(); }}
        />
      )}
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

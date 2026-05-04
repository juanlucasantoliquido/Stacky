import React, { useState, useEffect, useCallback } from "react";
import type { VsCodeAgent } from "../types";
import { Agents } from "../api/endpoints";
import { getPinnedAgents } from "../services/preferences";
import EmployeeCard from "../components/EmployeeCard";
import TeamManageDrawer from "../components/TeamManageDrawer";
import EmployeeEditDrawer from "../components/EmployeeEditDrawer";
import styles from "./TeamScreen.module.css";

interface TeamScreenProps {
  onGoToWorkbench: () => void;
}

export default function TeamScreen({ onGoToWorkbench }: TeamScreenProps) {
  const [allAgents, setAllAgents] = useState<VsCodeAgent[]>([]);
  const [pinned, setPinned] = useState<string[]>(getPinnedAgents());
  const [manageOpen, setManageOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setPinned([...getPinnedAgents()]);
  }, []);

  useEffect(() => {
    Agents.vsCodeAgents()
      .then(setAllAgents)
      .catch(() => setAllAgents([]))
      .finally(() => setLoading(false));
  }, []);

  function agentByFilename(filename: string): VsCodeAgent | undefined {
    return allAgents.find((a) => a.filename === filename);
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
          <button className={styles.workbenchBtn} onClick={onGoToWorkbench}>
            Ir al Workbench →
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
            {pinned.map((filename) => (
              <EmployeeCard
                key={filename}
                filename={filename}
                agent={agentByFilename(filename)}
                onEdit={(f) => setEditTarget(f)}
                onRemoved={refresh}
              />
            ))}
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

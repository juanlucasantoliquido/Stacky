import { useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkbench } from "../store/workbench";
import { Projects } from "../api/endpoints";
import type { Project } from "../types";
import NewProjectModal from "./NewProjectModal";
import EditProjectModal from "./EditProjectModal";
import styles from "./TopBar.module.css";

interface TopBarProps {
  onGoToTeam?: () => void;
}

export default function TopBar({ onGoToTeam }: TopBarProps) {
  const runningExecutionId = useWorkbench((s) => s.runningExecutionId);
  const isRunning = runningExecutionId != null;
  const setActiveProject = useWorkbench((s) => s.setActiveProject);
  const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
  const queryClient = useQueryClient();

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectName, setActiveProjectName] = useState<string>("");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [editProjectOpen, setEditProjectOpen] = useState(false);

  const activeProject = projects.find((p) => p.name === activeProjectName) ?? null;

  /** Carga los agentes fijados de un proyecto y los mete en el store. */
  const loadProjectAgents = useCallback(async (name: string) => {
    try {
      const res = await Projects.getAgents(name);
      setPinnedAgents(res.pinned_agents ?? []);
    } catch {
      setPinnedAgents([]);
    }
  }, [setPinnedAgents]);

  async function loadProjects() {
    try {
      const res = await Projects.list();
      setProjects(res.projects ?? []);
      const active = (res.projects ?? []).find((p: Project) => p.active);
      if (active) {
        setActiveProjectName(active.name);
        setActiveProject(active);
        await loadProjectAgents(active.name);
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => { loadProjects(); }, []);

  async function handleProjectChange(name: string) {
    setActiveProjectName(name);
    try {
      const res = await Projects.setActive(name);
      if (res.project) setActiveProject(res.project);
      await loadProjectAgents(name);
      // Invalidar caché de tickets para que se recarguen del proyecto nuevo
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
    } catch {
      // ignore
    }
  }

  function handleProjectCreated(name: string, _displayName: string) {
    loadProjects();
    handleProjectChange(name);
  }

  async function handleDeleteProject(name: string) {
    if (!window.confirm(`¿Eliminar el proyecto "${name}"? Esta acción no se puede deshacer.`)) return;
    try {
      await Projects.remove(name);
      await loadProjects();
    } catch (e: any) {
      window.alert(`Error al eliminar: ${e?.message || e}`);
    }
  }

  return (
    <header className={styles.bar}>
      <div className={styles.main}>
        <div className={styles.brand}>
          {onGoToTeam && (
            <button className={styles.teamBtn} onClick={onGoToTeam} title="Volver al equipo">
              ← Equipo
            </button>
          )}
          <img
            src="/stacky-agents-logo.svg"
            alt="Stacky"
            className={styles.logoImg}
            width={22}
            height={22}
          />
          Stacky
        </div>
        <div className={styles.project}>
          <span className={styles.projectLabel}>Proyecto</span>
          {projects.length > 0 ? (
            <select
              className={styles.projectSelect}
              value={activeProjectName}
              onChange={(e) => handleProjectChange(e.target.value)}
            >
              {projects.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.display_name || p.name}
                  {p.has_credentials === false ? " ⚠" : ""}
                </option>
              ))}
            </select>
          ) : (
            <strong className={styles.projectFallback}>Sin proyectos</strong>
          )}
          {activeProject && (
            <button
              className={styles.editProjectBtn}
              title="Editar proyecto activo"
              onClick={() => setEditProjectOpen(true)}
            >
              ✎
            </button>
          )}
          <button
            className={styles.newProjectBtn}
            title="Inicializar nuevo proyecto"
            onClick={() => setNewProjectOpen(true)}
          >
            +
          </button>
        </div>
        <div className={styles.actions}>
          {isRunning && (
            <span className={styles.runningBadge}>
              <span className={styles.badgeSpinner} aria-hidden="true" />
              Agente trabajando…
            </span>
          )}
          <span>dev@local</span>
        </div>
      </div>
      {isRunning && <div className={styles.progressBar} role="progressbar" aria-label="Ejecución en progreso" />}
      {newProjectOpen && (
        <NewProjectModal
          onClose={() => setNewProjectOpen(false)}
          onCreated={handleProjectCreated}
        />
      )}
      {editProjectOpen && activeProject && (
        <EditProjectModal
          project={activeProject}
          onClose={() => setEditProjectOpen(false)}
          onSaved={() => { setEditProjectOpen(false); loadProjects(); }}
          onDelete={() => { setEditProjectOpen(false); handleDeleteProject(activeProject.name); }}
        />
      )}
    </header>
  );
}


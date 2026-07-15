import { useState, useEffect, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkbench } from "../store/workbench";
import { useActiveRunsGlobal } from "../hooks/useActiveRunsGlobal";
import { Projects, Health } from "../api/endpoints";
import type { AgentWorkflowConfig, Project } from "../types";
import NewProjectModal from "./NewProjectModal";
import EditProjectModal from "./EditProjectModal";
import StreakBadge from "./StreakBadge";
import CostCapIndicator from "./CostCapIndicator";
import styles from "./TopBar.module.css";

interface TopBarProps {
  onGoToTeam?: () => void;
  shellV2?: boolean;   // Plan 139 — aplica el re-estilo v2 (aditivo)
}

export default function TopBar({ onGoToTeam, shellV2 }: TopBarProps) {
  // Plan 134 F4: fuente VIVA — la misma query compartida del panel global
  // (services/activeRuns.ts). El campo de workbench que este badge leía antes
  // estaba muerto: solo lo seteaba useAgentRun (consumidor huérfano
  // InputContextEditor) y los flujos reales (launchAgentWithRuntime) nunca lo
  // tocaron (grep gate del plan: 0 referencias al nombre viejo en este archivo).
  const activeRunsCount = useActiveRunsGlobal().data?.length ?? 0;
  const isRunning = activeRunsCount > 0;
  const setActiveProject = useWorkbench((s) => s.setActiveProject);
  const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
  const setTeamLoading = useWorkbench((s) => s.setTeamLoading);
  const setGetAgentsError = useWorkbench((s) => s.setGetAgentsError);
  const queryClient = useQueryClient();

  /** Contador incremental para detectar y descartar respuestas de requests anteriores. */
  const loadSeq = useRef(0);

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectName, setActiveProjectName] = useState<string>("");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [editProjectOpen, setEditProjectOpen] = useState(false);
  const [version, setVersion] = useState<string | null>(null);

  const activeProject = projects.find((p) => p.name === activeProjectName) ?? null;

  /** Carga los agentes fijados de un proyecto y los mete en el store. */
  const loadProjectAgents = useCallback(async (name: string) => {
    const seq = ++loadSeq.current;
    setTeamLoading(true);
    setGetAgentsError(null);
    // Limpiar estado del proyecto anterior inmediatamente
    setPinnedAgents([]);
    setAgentWorkflows({});
    try {
      const res = await Projects.getAgents(name);
      if (seq !== loadSeq.current) return; // request obsoleta — ignorar
      const agents = res.pinned_agents ?? [];
      setPinnedAgents(agents);
      // Cargar workflow de cada agente y guardar en store
      const wfMap: Record<string, AgentWorkflowConfig> = {};
      await Promise.all(
        agents.map(async (filename) => {
          try {
            const wf = await Projects.getAgentWorkflow(name, filename);
            if (wf.ok) {
              wfMap[filename] = {
                allowed_states: wf.allowed_states ?? [],
                transition_state: wf.transition_state ?? "",
                requires_prior_output: wf.requires_prior_output ?? false,
              };
            }
          } catch { /* ignore workflow individual */ }
        })
      );
      if (seq !== loadSeq.current) return; // cambio de proyecto mientras cargaba workflows
      setAgentWorkflows(wfMap);
    } catch {
      if (seq !== loadSeq.current) return;
      setPinnedAgents([]);
      setAgentWorkflows({});
      setGetAgentsError("No se pudieron cargar los empleados del proyecto. Reintentá o revisá logs.");
    } finally {
      if (seq === loadSeq.current) setTeamLoading(false);
    }
  }, [setPinnedAgents, setAgentWorkflows, setTeamLoading, setGetAgentsError]);

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

  useEffect(() => {
    Health.get()
      .then((res) => { if (res.version) setVersion(res.version); })
      .catch(() => { /* ignorar: no crítico */ });
  }, []);

  async function handleProjectChange(name: string) {
    setActiveProjectName(name);
    try {
      const res = await Projects.setActive(name);
      if (res.project) setActiveProject(res.project);
      await loadProjectAgents(name);
      // Limpiar caches sensibles al proyecto para no mostrar datos viejos
      queryClient.removeQueries({ queryKey: ["tickets"] });
      queryClient.removeQueries({ queryKey: ["tickets-hierarchy"] });
      queryClient.removeQueries({ queryKey: ["flow-config"] });
      queryClient.removeQueries({ queryKey: ["ticket-sync"] });
      queryClient.removeQueries({ queryKey: ["executions-active"] });
      queryClient.removeQueries({ queryKey: ["executions-queued"] });
      queryClient.invalidateQueries({ queryKey: ["vscode-agents"] });
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
    <header className={`${styles.bar} ${shellV2 ? styles.barV2 : ""}`}>
      <div className={styles.main}>
        <div className={styles.brand}>
          {onGoToTeam && (
            <button className={styles.teamBtn} onClick={onGoToTeam} title="Volver al equipo">
              ← Equipo
            </button>
          )}
          <img
            src="/Logo_ubimia_verde_u.png"
            alt="Ubimia"
            className={styles.ubimiaLogo}
            height={20}
          />
          <span className={styles.brandDivider} aria-hidden="true" />
          <img
            src="/stacky-pixel.svg"
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
              {activeRunsCount === 1
                ? "Agente trabajando…"
                : `${activeRunsCount} agentes trabajando…`}
            </span>
          )}
          <CostCapIndicator projectName={activeProjectName || null} />
          <StreakBadge />
          <span className={styles.version} title={version ? `Versión ${version}` : "dev@local"}>{version ? `v${version}` : "dev@local"}</span>
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


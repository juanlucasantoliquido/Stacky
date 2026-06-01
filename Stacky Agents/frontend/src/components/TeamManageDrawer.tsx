import React, { useState, useEffect } from "react";
import type { VsCodeAgent } from "../types";
import type { AgentWorkflowConfig } from "../types";
import {
  getAgentAvatar,
  setAgentAvatar,
  getAgentNickname,
  setAgentNickname,
  getAgentRole,
  setAgentRole,
} from "../services/preferences";
import { Agents, Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import AgentWorkflowForm from "./AgentWorkflowForm";
import type { AgentWorkflowFormValue } from "./AgentWorkflowForm";
import PixelAvatar from "./PixelAvatar";
import AvatarPicker from "./AvatarPicker";
import styles from "./TeamManageDrawer.module.css";

interface TeamManageDrawerProps {
  allAgents: VsCodeAgent[];
  onClose: () => void;
}

interface PendingAdd {
  filename: string;
  agentName: string;
  avatar: string | null;
  nickname: string;
  role: string;
}

export default function TeamManageDrawer({ allAgents, onClose }: TeamManageDrawerProps) {
  // ─── Fuente de verdad: store por proyecto ──────────────────────────────────
  const activeProject = useWorkbench((s) => s.activeProject);
  const setActiveProject = useWorkbench((s) => s.setActiveProject);
  const pinned = useWorkbench((s) => s.pinnedAgents);
  const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);

  const [pendingAdd, setPendingAdd] = useState<PendingAdd | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Fuente canónica resuelta dinámicamente desde el backend (plan
  // plan-agentes-bundled-en-stacky-2026-05-29): muestra dónde vive realmente
  // el .agent.md que el operador está viendo. Reemplaza el texto hardcoded
  // a `%APPDATA%/Code/User/prompts` que mentía en deploys nuevos.
  const [agentsDir, setAgentsDir] = useState<string>("");
  const [displayAgents, setDisplayAgents] = useState<VsCodeAgent[]>(allAgents);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [savingSource, setSavingSource] = useState(false);
  // filename → ruta absoluta del .agent.md según el manifest canónico. La UI la
  // muestra por agente para que el operador confirme qué archivo usará el runner
  // (plan-agentes-bundled-en-stacky-2026-05-29 §3.4).
  const [agentPaths, setAgentPaths] = useState<Record<string, string>>({});

  // Ruta efectiva del .agent.md para `filename`. Prefiere el `path` exacto del
  // manifest (carpeta canónica) y cae a `agentsDir + filename` cuando hay un
  // override de carpeta por proyecto que el manifest canónico no refleja.
  function pathForAgent(filename: string): string {
    const fromManifest = agentPaths[filename];
    if (fromManifest) return fromManifest;
    if (!agentsDir) return filename;
    const sep = agentsDir.includes("\\") ? "\\" : "/";
    const base = agentsDir.endsWith(sep) ? agentsDir.slice(0, -sep.length) : agentsDir;
    return `${base}${sep}${filename}`;
  }

  function applyManifest(manifest: Awaited<ReturnType<typeof Agents.stackyManifest>> | null) {
    setAgentsDir(manifest?.effective_agents_dir || manifest?.agents_dir || "");
    const map: Record<string, string> = {};
    for (const a of manifest?.agents ?? []) {
      if (a.filename && a.path) map[a.filename] = a.path;
    }
    setAgentPaths(map);
  }

  async function reloadAgentsSource() {
    setLoadingAgents(true);
    try {
      const [manifest, agents] = await Promise.all([
        Agents.stackyManifest().catch(() => null),
        Agents.vsCodeAgents(),
      ]);
      applyManifest(manifest);
      setDisplayAgents(agents);
    } catch {
      setDisplayAgents([]);
      setAgentsDir("");
      setAgentPaths({});
    } finally {
      setLoadingAgents(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoadingAgents(true);
    Promise.all([
      Agents.stackyManifest().catch(() => null),
      Agents.vsCodeAgents(),
    ])
      .then(([manifest, agents]) => {
        if (cancelled) return;
        applyManifest(manifest);
        setDisplayAgents(agents);
      })
      .catch(() => {
        if (cancelled) return;
        setAgentsDir("");
        setAgentPaths({});
        setDisplayAgents([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingAgents(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── Workflow state para el modal de alta ─────────────────────────────
  const [pendingWorkflow, setPendingWorkflow] = useState<AgentWorkflowFormValue>({
    allowed_states: [],
    transition_state: "",
    requires_prior_output: false,
  });
  const [trackerStates, setTrackerStates] = useState<string[]>([]);
  const [loadingTrackerStates, setLoadingTrackerStates] = useState(false);
  const [trackerLoadError, setTrackerLoadError] = useState(false);
  // true = agent ya persistió, sólo faltó el workflow
  const [agentAlreadySaved, setAgentAlreadySaved] = useState(false);

  // Close config modal with Escape
  useEffect(() => {
    if (!pendingAdd) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") handleCancelModal(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [pendingAdd]);

  function isInTeam(filename: string) {
    return pinned.includes(filename);
  }

  function handleCancelModal() {
    if (!agentAlreadySaved) setPendingAdd(null);
    else setPendingAdd(null); // permite cerrar aunque el agente ya fue guardado
    setAgentAlreadySaved(false);
    setSaveError(null);
  }

  async function handleSelectForAdd(agent: VsCodeAgent) {
    if (!activeProject || saving) return;
    if (isInTeam(agent.filename)) {
      const nextPinned = pinned.filter((f) => f !== agent.filename);
      setSaving(true);
      setSaveError(null);
      try {
        await Projects.putAgents(activeProject.name, nextPinned);
        setPinnedAgents(nextPinned);
      } catch {
        setSaveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
      } finally {
        setSaving(false);
      }
      return;
    }
    // Resetear estado del modal
    setPendingWorkflow({ allowed_states: [], transition_state: "", requires_prior_output: false });
    setAgentAlreadySaved(false);
    setSaveError(null);
    setPendingAdd({
      filename: agent.filename,
      agentName: agent.name,
      avatar: getAgentAvatar(agent.filename),
      nickname: getAgentNickname(agent.filename) ?? "",
      role: getAgentRole(agent.filename) ?? "",
    });
    // Cargar tracker states en paralelo
    if (activeProject) {
      setLoadingTrackerStates(true);
      setTrackerLoadError(false);
      Projects.trackerStates(activeProject.name)
        .then((r) => { if (r.ok) setTrackerStates(r.states ?? []); })
        .catch(() => setTrackerLoadError(true))
        .finally(() => setLoadingTrackerStates(false));
    }
  }

  async function handleChangeAgentsDir() {
    if (!activeProject || savingSource) return;
    setSavingSource(true);
    setSaveError(null);
    try {
      const picked = await Projects.browseFolder({
        title: "Seleccionar carpeta de agentes",
        initial_dir: agentsDir || activeProject.agents_dir || activeProject.workspace_root || "",
      });
      if (!picked.ok || !picked.path) {
        setSaveError(picked.error || "No se pudo seleccionar la carpeta de agentes.");
        return;
      }
      const saved = await Projects.update(activeProject.name, { agents_dir: picked.path });
      if (!saved.ok) {
        setSaveError("No se pudo guardar la carpeta de agentes del proyecto.");
        return;
      }
      setActiveProject(saved.project);
      setAgentsDir(saved.project.agents_dir || picked.path);
      await reloadAgentsSource();
    } catch {
      setSaveError("No se pudo cambiar la carpeta de agentes. Reintentá o revisá logs.");
    } finally {
      setSavingSource(false);
    }
  }

  async function handleConfirmAdd() {
    if (!pendingAdd || !activeProject || saving) return;

    setSaving(true);
    setSaveError(null);

    // Paso 1: persistir membresía (saltar si ya se guardó en intento anterior)
    if (!agentAlreadySaved) {
      if (pendingAdd.avatar) setAgentAvatar(pendingAdd.filename, pendingAdd.avatar);
      if (pendingAdd.nickname.trim()) setAgentNickname(pendingAdd.filename, pendingAdd.nickname.trim());
      if (pendingAdd.role.trim()) setAgentRole(pendingAdd.filename, pendingAdd.role.trim());
      const nextPinned = pinned.includes(pendingAdd.filename)
        ? pinned
        : [...pinned, pendingAdd.filename];
      try {
        await Projects.putAgents(activeProject.name, nextPinned);
        setPinnedAgents(nextPinned);
        setAgentAlreadySaved(true);
      } catch {
        setSaveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
        setSaving(false);
        return;
      }
    }

    // Paso 2: persistir workflow
    try {
      const wf: AgentWorkflowConfig = {
        allowed_states: pendingWorkflow.allowed_states,
        transition_state: pendingWorkflow.transition_state,
        requires_prior_output: pendingWorkflow.requires_prior_output,
      };
      await Projects.putAgentWorkflow(activeProject.name, pendingAdd.filename, wf);
      setAgentWorkflows({ ...agentWorkflows, [pendingAdd.filename]: wf });
      // Éxito total: cerrar modal
      setPendingAdd(null);
      setAgentAlreadySaved(false);
    } catch {
      setSaveError(
        "El empleado se agregó, pero no se pudo guardar su workflow. ¡Comletá el workflow antes de usarlo."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* ─── Side drawer — agent list ─── */}
      <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className={styles.drawer}>

          <div className={styles.header}>
            <h2 className={styles.title}>Agentes Stacky disponibles</h2>
            <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
          </div>

          <div className={styles.hint}>
            <span className={styles.hintText}>
              📁 Fuente: <code>{agentsDir || "Stacky/agents (resolviendo…)"}</code>
            </span>
            <button
              type="button"
              className={styles.sourceBtn}
              onClick={handleChangeAgentsDir}
              disabled={!activeProject || savingSource}
            >
              {savingSource ? "Guardando..." : "Cambiar"}
            </button>
          </div>

          {!activeProject && (
            <div className={styles.empty}>
              Seleccioná un proyecto activo antes de agregar o quitar empleados.
            </div>
          )}

          {saveError && (
            <div className={styles.errorBanner} role="alert">
              ⚠ {saveError}
            </div>
          )}

          {loadingAgents ? (
            <div className={styles.empty}>
              Cargando agentes desde <code>{agentsDir || "la fuente configurada"}</code>...
            </div>
          ) : displayAgents.length === 0 ? (
            <div className={styles.empty}>
              No se encontraron agentes en <code>{agentsDir || "Stacky/agents"}</code>.
              Importá los <code>.agent.md</code> desde el panel de configuración o
              colocá los archivos directamente en esa carpeta.
            </div>
          ) : (
            <div className={styles.list}>
              {displayAgents.map((agent) => {
                const inTeam = isInTeam(agent.filename);
                const avatar = getAgentAvatar(agent.filename);
                const agentPath = pathForAgent(agent.filename);

                return (
                  <div key={agent.filename} className={inTeam ? styles.agentRowDone : styles.agentRow}>
                    <PixelAvatar value={avatar} size="sm" name={agent.name} />
                    <div className={styles.agentInfo}>
                      <span className={styles.agentName}>{agent.name}</span>
                      <span className={styles.agentDesc}>
                        {agent.description?.slice(0, 80) ?? agent.filename}
                      </span>
                      <span className={styles.agentPath} title={agentPath}>
                        {/* bidi isolate: la ruta es LTR dentro de un contenedor rtl */}
                        <bdi>{agentPath}</bdi>
                      </span>
                    </div>
                    {inTeam && <span className={styles.inTeamBadge}>✓</span>}
                    <button
                      className={inTeam ? styles.removeBtn : styles.addBtn}
                      onClick={() => handleSelectForAdd(agent)}
                      disabled={saving || !activeProject}
                    >
                      {saving && inTeam ? "Guardando…" : inTeam ? "Quitar" : "+ Agregar"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div className={styles.footer}>
            <button className={styles.doneBtn} onClick={onClose}>Listo</button>
          </div>
        </div>
      </div>

      {/* ─── Centered config modal (rendered over everything) ─── */}
      {pendingAdd && (
        <div
          className={styles.modalBackdrop}
          onClick={(e) => e.target === e.currentTarget && handleCancelModal()}
        >
          <div className={styles.modal} role="dialog" aria-modal="true">

            {/* Avatar — hero visual */}
            <div className={styles.modalAvatar}>
              <PixelAvatar value={pendingAdd.avatar} size="lg" name={pendingAdd.agentName} />
            </div>

            <h3 className={styles.modalAgentName}>{pendingAdd.agentName}</h3>
            <p className={styles.modalSubtitle}>Personalizá tu nuevo empleado</p>

            {/* Name + Role — ocultar si ya se guardó el empleado (sólo falta workflow) */}
            {!agentAlreadySaved && (
              <>
                <div className={styles.modalFields}>
                  <div className={styles.modalField}>
                    <label className={styles.modalLabel}>Apodo</label>
                    <input
                      className={styles.modalInput}
                      placeholder={pendingAdd.agentName}
                      value={pendingAdd.nickname}
                      onChange={(e) => setPendingAdd({ ...pendingAdd, nickname: e.target.value })}
                      autoFocus
                    />
                  </div>
                  <div className={styles.modalField}>
                    <label className={styles.modalLabel}>Rol</label>
                    <input
                      className={styles.modalInput}
                      placeholder="ej: Analista Senior"
                      value={pendingAdd.role}
                      onChange={(e) => setPendingAdd({ ...pendingAdd, role: e.target.value })}
                    />
                  </div>
                </div>

                {/* Avatar picker — main focus */}
                <div className={styles.modalPickerSection}>
                  <label className={styles.modalLabel}>Avatar</label>
                  <AvatarPicker
                    value={pendingAdd.avatar}
                    onChange={(v) => setPendingAdd({ ...pendingAdd, avatar: v })}
                  />
                </div>
              </>
            )}

            {/* Workflow — sección siempre visible en el modal */}
            <div className={styles.modalWorkflowSection}>
              <p className={styles.modalLabel}>⚙️ Configuración de workflow</p>
              <AgentWorkflowForm
                value={pendingWorkflow}
                onChange={setPendingWorkflow}
                trackerStates={trackerStates}
                loadingStates={loadingTrackerStates}
                loadError={trackerLoadError}
                projectDisplayName={activeProject?.display_name ?? activeProject?.name}
              />
            </div>

            {saveError && (
              <div className={styles.errorBanner} role="alert">
                ⚠ {saveError}
              </div>
            )}

            {/* Actions */}
            <div className={styles.modalActions}>
              <button className={styles.modalCancelBtn} onClick={handleCancelModal} disabled={saving}>
                {agentAlreadySaved ? "Cerrar" : "Cancelar"}
              </button>
              <button className={styles.modalConfirmBtn} onClick={handleConfirmAdd} disabled={saving}>
                {saving
                  ? "Guardando…"
                  : agentAlreadySaved
                  ? "↺ Reintentar workflow"
                  : "✓ Agregar al equipo"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

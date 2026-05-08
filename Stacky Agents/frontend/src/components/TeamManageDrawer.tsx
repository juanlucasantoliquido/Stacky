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
import { Projects } from "../api/endpoints";
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
  const pinned = useWorkbench((s) => s.pinnedAgents);
  const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);

  const [pendingAdd, setPendingAdd] = useState<PendingAdd | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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
            <h2 className={styles.title}>Agentes disponibles en VS Code</h2>
            <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
          </div>

          <p className={styles.hint}>
            📁 Fuente: <code>%APPDATA%/Code/User/prompts</code>
          </p>

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

          {allAgents.length === 0 ? (
            <div className={styles.empty}>
              No se encontraron agentes. Verificá que VS Code esté corriendo con la extensión Stacky.
            </div>
          ) : (
            <div className={styles.list}>
              {allAgents.map((agent) => {
                const inTeam = isInTeam(agent.filename);
                const avatar = getAgentAvatar(agent.filename);

                return (
                  <div key={agent.filename} className={inTeam ? styles.agentRowDone : styles.agentRow}>
                    <PixelAvatar value={avatar} size="sm" name={agent.name} />
                    <div className={styles.agentInfo}>
                      <span className={styles.agentName}>{agent.name}</span>
                      <span className={styles.agentDesc}>
                        {agent.description?.slice(0, 80) ?? agent.filename}
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

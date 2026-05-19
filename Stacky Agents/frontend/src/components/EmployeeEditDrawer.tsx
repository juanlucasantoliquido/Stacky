import React, { useState, useEffect } from "react";
import type { VsCodeAgent } from "../types";
import {
  getAgentAvatar,
  setAgentAvatar,
  getAgentNickname,
  setAgentNickname,
  getAgentRole,
  setAgentRole,
  getAgentType,
  setAgentType,
} from "../services/preferences";

const VALID_AGENT_TYPES = [
  "business",
  "functional",
  "technical",
  "developer",
  "qa",
] as const;
type AgentTypeOption = (typeof VALID_AGENT_TYPES)[number] | "";

// Heurística usada cuando el operador no fijó un tipo explícito.
function inferTypeFromFilename(filename: string): AgentTypeOption {
  const f = filename.toLowerCase();
  if (f.includes("business") || f.includes("negocio")) return "business";
  if (f.includes("functional") || f.includes("funcional")) return "functional";
  if (f.includes("technical") || f.includes("tecnico") || f.includes("técnico")) return "technical";
  if (f.includes("dev") || f.includes("developer")) return "developer";
  if (f.includes("qa") || f.includes("test")) return "qa";
  return "";
}
import { Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import AgentWorkflowForm from "./AgentWorkflowForm";
import type { AgentWorkflowFormValue } from "./AgentWorkflowForm";
import AvatarPicker from "./AvatarPicker";
import PixelAvatar from "./PixelAvatar";
import styles from "./EmployeeEditDrawer.module.css";

interface EmployeeEditDrawerProps {
  filename: string;
  agent: VsCodeAgent | undefined;
  onClose: () => void;
  onRemoved: () => void;
}

export default function EmployeeEditDrawer({ filename, agent, onClose, onRemoved }: EmployeeEditDrawerProps) {
  const defaultName = agent?.name ?? filename.replace(/\.agent\.md$/i, "");
  const defaultRole = agent?.description?.split(".")[0] ?? "Agente VS Code";

  const [nickname, setNickname] = useState(getAgentNickname(filename) ?? "");
  const [role, setRole] = useState(getAgentRole(filename) ?? "");
  const [avatar, setAvatar] = useState<string | null>(getAgentAvatar(filename));
  const [agentTypeValue, setAgentTypeValue] = useState<AgentTypeOption>(
    (getAgentType(filename) as AgentTypeOption) ?? ""
  );
  const inferredType = inferTypeFromFilename(filename);
  const [confirmRemove, setConfirmRemove] = useState(false);

  // Workflow config
  const activeProject = useWorkbench((s) => s.activeProject);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const [trackerStates, setTrackerStates] = useState<string[]>([]);
  const [trackerLoadError, setTrackerLoadError] = useState(false);
  const [loadingTrackerStates, setLoadingTrackerStates] = useState(false);
  const [workflow, setWorkflow] = useState<AgentWorkflowFormValue>({
    allowed_states: [],
    transition_state: "",
    requires_prior_output: false,
  });
  const [savingWf, setSavingWf] = useState(false);
  const [wfSaved, setWfSaved] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    // Cargar estados del tracker
    setLoadingTrackerStates(true);
    setTrackerLoadError(false);
    Projects.trackerStates(activeProject.name)
      .then((r) => { if (r.ok) setTrackerStates(r.states ?? []); })
      .catch(() => setTrackerLoadError(true))
      .finally(() => setLoadingTrackerStates(false));
    // Cargar workflow actual del agente
    Projects.getAgentWorkflow(activeProject.name, filename)
      .then((r) => {
        if (r.ok) {
          setWorkflow({
            allowed_states: r.allowed_states ?? [],
            transition_state: r.transition_state ?? "",
            requires_prior_output: r.requires_prior_output ?? false,
          });
        }
      })
      .catch(() => {});
  }, [activeProject, filename]);

  async function handleSaveWorkflow() {
    if (!activeProject) return;
    setSavingWf(true);
    try {
      await Projects.putAgentWorkflow(activeProject.name, filename, {
        allowed_states: workflow.allowed_states,
        transition_state: workflow.transition_state,
        requires_prior_output: workflow.requires_prior_output,
      });
      // Actualizar store
      setAgentWorkflows({
        ...agentWorkflows,
        [filename]: {
          allowed_states: workflow.allowed_states,
          transition_state: workflow.transition_state,
          requires_prior_output: workflow.requires_prior_output,
        },
      });
      setWfSaved(true);
      setTimeout(() => setWfSaved(false), 2000);
    } catch { /* ignore */ }
    finally { setSavingWf(false); }
  }

  function handleSave() {
    if (avatar) setAgentAvatar(filename, avatar);
    setAgentNickname(filename, nickname.trim() || defaultName);
    setAgentRole(filename, role.trim() || defaultRole);
    setAgentType(filename, agentTypeValue);
    onClose();
  }

  function handleRemove() {
    // Membresía persiste vía Projects.putAgents — el padre maneja el remove.
    onRemoved();
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.drawer}>
        <div className={styles.header}>
          <PixelAvatar value={avatar} size="md" name={nickname || defaultName} />
          <div className={styles.headerText}>
            <h2 className={styles.title}>Editar empleado</h2>
            <span className={styles.filename}>{filename}</span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">✕</button>
        </div>

        <div className={styles.body}>
          {/* Nickname */}
          <div className={styles.field}>
            <label className={styles.label}>Apodo</label>
            <input
              className={styles.input}
              type="text"
              placeholder={defaultName}
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
            />
          </div>

          {/* Role */}
          <div className={styles.field}>
            <label className={styles.label}>Rol</label>
            <input
              className={styles.input}
              type="text"
              placeholder={defaultRole}
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
          </div>

          {/* Tipo de agente — override explícito sobre la heurística del filename */}
          <div className={styles.field}>
            <label className={styles.label}>Tipo de agente</label>
            <select
              className={styles.input}
              value={agentTypeValue}
              onChange={(e) => setAgentTypeValue(e.target.value as AgentTypeOption)}
            >
              <option value="">
                {inferredType
                  ? `Auto (${inferredType})`
                  : "Auto (sin detectar)"}
              </option>
              {VALID_AGENT_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <span style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4, display: "block" }}>
              Usado por "Config de Flujo" para resolver el agente sugerido por estado ADO.
            </span>
          </div>

          {/* Avatar picker */}
          <div className={styles.field}>
            <label className={styles.label}>Avatar</label>
            <AvatarPicker value={avatar} onChange={(v) => setAvatar(v)} />
          </div>

          {/* ── Workflow de estados ────────────────────────────── */}
          {activeProject && (
            <div className={styles.field}>
              <label className={styles.label}>
                ⚙️ Workflow
                <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-faint)", marginLeft: 8 }}>
                  {activeProject.display_name ?? activeProject.name}
                </span>
              </label>
              <AgentWorkflowForm
                value={workflow}
                onChange={setWorkflow}
                trackerStates={trackerStates}
                loadingStates={loadingTrackerStates}
                loadError={trackerLoadError}
                projectDisplayName={activeProject.display_name ?? activeProject.name}
              />
              <button
                type="button"
                className={styles.saveBtn}
                style={{ marginTop: 10, fontSize: 13 }}
                onClick={handleSaveWorkflow}
                disabled={savingWf || !activeProject}
              >
                {savingWf ? "Guardando…" : wfSaved ? "✓ Guardado" : "💾 Guardar configuración de estados"}
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          {confirmRemove ? (
            <div className={styles.confirmRow}>
              <span className={styles.confirmText}>¿Quitar del equipo?</span>
              <button className={styles.cancelBtn} onClick={() => setConfirmRemove(false)}>No</button>
              <button className={styles.dangerBtn} onClick={handleRemove}>Sí, quitar</button>
            </div>
          ) : (
            <button
              className={styles.removeBtn}
              onClick={() => setConfirmRemove(true)}
            >
              🗑️ Quitar del equipo
            </button>
          )}
          <div className={styles.mainActions}>
            <button className={styles.cancelBtn} onClick={onClose}>Cancelar</button>
            <button className={styles.saveBtn} onClick={handleSave}>Guardar</button>
          </div>
        </div>
      </div>
    </div>
  );
}

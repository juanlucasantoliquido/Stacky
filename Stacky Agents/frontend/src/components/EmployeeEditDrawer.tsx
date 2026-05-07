import React, { useState, useEffect } from "react";
import type { VsCodeAgent } from "../types";
import {
  getAgentAvatar,
  setAgentAvatar,
  getAgentNickname,
  setAgentNickname,
  getAgentRole,
  setAgentRole,
  removePinnedAgent,
} from "../services/preferences";
import { Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
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
  const [confirmRemove, setConfirmRemove] = useState(false);

  // Workflow config
  const activeProject = useWorkbench((s) => s.activeProject);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const [trackerStates, setTrackerStates] = useState<string[]>([]);
  const [allowedStates, setAllowedStates] = useState<string[]>([]);
  const [transitionState, setTransitionState] = useState<string>("");
  const [requiresPriorOutput, setRequiresPriorOutput] = useState(false);
  const [savingWf, setSavingWf] = useState(false);
  const [wfSaved, setWfSaved] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    // Cargar estados del tracker
    Projects.trackerStates(activeProject.name)
      .then((r) => { if (r.ok) setTrackerStates(r.states ?? []); })
      .catch(() => {});
    // Cargar workflow actual del agente
    Projects.getAgentWorkflow(activeProject.name, filename)
      .then((r) => {
        if (r.ok) {
          setAllowedStates(r.allowed_states ?? []);
          setTransitionState(r.transition_state ?? "");
          setRequiresPriorOutput(r.requires_prior_output ?? false);
        }
      })
      .catch(() => {});
  }, [activeProject, filename]);

  async function handleSaveWorkflow() {
    if (!activeProject) return;
    setSavingWf(true);
    try {
      await Projects.putAgentWorkflow(activeProject.name, filename, {
        allowed_states: allowedStates,
        transition_state: transitionState,
        requires_prior_output: requiresPriorOutput,
      });
      // Actualizar store
      setAgentWorkflows({ ...agentWorkflows, [filename]: { allowed_states: allowedStates, transition_state: transitionState, requires_prior_output: requiresPriorOutput } });
      setWfSaved(true);
      setTimeout(() => setWfSaved(false), 2000);
    } catch { /* ignore */ }
    finally { setSavingWf(false); }
  }

  function toggleState(state: string) {
    setAllowedStates((prev) =>
      prev.includes(state) ? prev.filter((s) => s !== state) : [...prev, state]
    );
  }

  function handleSave() {
    if (avatar) setAgentAvatar(filename, avatar);
    setAgentNickname(filename, nickname.trim() || defaultName);
    setAgentRole(filename, role.trim() || defaultRole);
    onClose();
  }

  function handleRemove() {
    removePinnedAgent(filename);
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

          {/* Avatar picker */}
          <div className={styles.field}>
            <label className={styles.label}>Avatar</label>
            <AvatarPicker value={avatar} onChange={(v) => setAvatar(v)} />
          </div>

          {/* ── Workflow de estados ────────────────────────────── */}
          {activeProject && (
            <div className={styles.field}>
              <label className={styles.label}>
                ⚙️ Estados visibles
                <span style={{ fontWeight: 400, fontSize: 11, color: "#94a3b8", marginLeft: 8 }}>
                  Qué tickets puede ver este empleado según su estado en {activeProject.display_name}
                </span>
              </label>
              {trackerStates.length === 0 ? (
                <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0" }}>
                  Sin estados disponibles. Configurá credenciales del proyecto para cargarlos automáticamente.
                </p>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  {trackerStates.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => toggleState(s)}
                      style={{
                        padding: "3px 10px",
                        borderRadius: 12,
                        fontSize: 12,
                        cursor: "pointer",
                        border: allowedStates.includes(s) ? "1.5px solid #3b82f6" : "1px solid #374151",
                        background: allowedStates.includes(s) ? "#1e3a5f" : "#1f2937",
                        color: allowedStates.includes(s) ? "#7dd3fc" : "#9ca3af",
                        fontWeight: allowedStates.includes(s) ? 600 : 400,
                      }}
                    >
                      {allowedStates.includes(s) ? "✓ " : ""}{s}
                    </button>
                  ))}
                </div>
              )}
              {allowedStates.length === 0 && trackerStates.length > 0 && (
                <p style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                  Sin selección = ve todos los estados.
                </p>
              )}

              <label className={styles.label} style={{ marginTop: 12 }}>
                Estado de transición al terminar
              </label>
              {trackerStates.length > 0 ? (
                <select
                  className={styles.input}
                  value={transitionState}
                  onChange={(e) => setTransitionState(e.target.value)}
                >
                  <option value="">— Sin transición automática —</option>
                  {trackerStates.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              ) : (
                <input
                  className={styles.input}
                  type="text"
                  placeholder="Ej: In Progress"
                  value={transitionState}
                  onChange={(e) => setTransitionState(e.target.value)}
                />
              )}

              <label className={styles.label} style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={requiresPriorOutput}
                  onChange={(e) => setRequiresPriorOutput(e.target.checked)}
                />
                Requiere output del agente anterior
              </label>

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

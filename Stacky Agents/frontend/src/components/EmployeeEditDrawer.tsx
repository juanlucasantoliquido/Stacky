import React, { useState } from "react";
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

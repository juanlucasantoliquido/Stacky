import React, { useState, useEffect } from "react";
import type { VsCodeAgent } from "../types";
import {
  getPinnedAgents,
  addPinnedAgent,
  removePinnedAgent,
  getAgentAvatar,
  setAgentAvatar,
  getAgentNickname,
  setAgentNickname,
  getAgentRole,
  setAgentRole,
} from "../services/preferences";
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
  const [pinned, setPinned] = useState<string[]>(() => getPinnedAgents());
  // null = list view · PendingAdd = centered config modal
  const [pendingAdd, setPendingAdd] = useState<PendingAdd | null>(null);

  // Close config modal with Escape
  useEffect(() => {
    if (!pendingAdd) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setPendingAdd(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [pendingAdd]);

  function isInTeam(filename: string) {
    return pinned.includes(filename);
  }

  function handleSelectForAdd(agent: VsCodeAgent) {
    if (isInTeam(agent.filename)) {
      removePinnedAgent(agent.filename);
      setPinned(getPinnedAgents());
      return;
    }
    setPendingAdd({
      filename: agent.filename,
      agentName: agent.name,
      avatar: getAgentAvatar(agent.filename),
      nickname: getAgentNickname(agent.filename) ?? "",
      role: getAgentRole(agent.filename) ?? "",
    });
  }

  function handleConfirmAdd() {
    if (!pendingAdd) return;
    if (pendingAdd.avatar) setAgentAvatar(pendingAdd.filename, pendingAdd.avatar);
    if (pendingAdd.nickname.trim()) setAgentNickname(pendingAdd.filename, pendingAdd.nickname.trim());
    if (pendingAdd.role.trim()) setAgentRole(pendingAdd.filename, pendingAdd.role.trim());
    addPinnedAgent(pendingAdd.filename);
    setPinned(getPinnedAgents());
    setPendingAdd(null);
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
                    >
                      {inTeam ? "Quitar" : "+ Agregar"}
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
          onClick={(e) => e.target === e.currentTarget && setPendingAdd(null)}
        >
          <div className={styles.modal} role="dialog" aria-modal="true">

            {/* Avatar — hero visual */}
            <div className={styles.modalAvatar}>
              <PixelAvatar value={pendingAdd.avatar} size="lg" name={pendingAdd.agentName} />
            </div>

            <h3 className={styles.modalAgentName}>{pendingAdd.agentName}</h3>
            <p className={styles.modalSubtitle}>Personalizá tu nuevo empleado</p>

            {/* Name + Role */}
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

            {/* Actions */}
            <div className={styles.modalActions}>
              <button className={styles.modalCancelBtn} onClick={() => setPendingAdd(null)}>
                Cancelar
              </button>
              <button className={styles.modalConfirmBtn} onClick={handleConfirmAdd}>
                ✓ Agregar al equipo
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

import React, { useState, useEffect } from "react";
import type { VsCodeAgent, AgentExecution } from "../types";
import {
  getPinnedAgents,
  getAgentAvatar,
  getAgentNickname,
  getAgentRole,
  removePinnedAgent,
  setAgentNickname,
  setAgentRole,
  setAgentAvatar,
} from "../services/preferences";
import { Agents } from "../api/endpoints";
import PixelAvatar from "./PixelAvatar";
import AgentLaunchModal from "./AgentLaunchModal";
import AgentHistoryModal from "./AgentHistoryModal";
import styles from "./EmployeeCard.module.css";

interface EmployeeCardProps {
  filename: string;
  agent: VsCodeAgent | undefined;
  onEdit: (filename: string) => void;
  onRemoved: () => void;
  runningExecution?: AgentExecution | null;
  runningTicketAdoId?: number | null;
}

const AGENT_TYPE_COLORS: Record<string, string> = {
  business:   "var(--agent-business)",
  functional: "var(--agent-functional)",
  technical:  "var(--agent-technical)",
  developer:  "var(--agent-developer)",
  qa:         "var(--agent-qa)",
  custom:     "var(--agent-custom)",
};

function inferType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("business") || f.includes("negocio")) return "business";
  if (f.includes("functional") || f.includes("funcional")) return "functional";
  if (f.includes("technical") || f.includes("tecnic")) return "technical";
  if (f.includes("dev") || f.includes("desarrollador")) return "developer";
  if (f.includes("qa") || f.includes("test")) return "qa";
  return "custom";
}

export default function EmployeeCard({ filename, agent, onEdit, onRemoved, runningExecution, runningTicketAdoId }: EmployeeCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const nickname = getAgentNickname(filename);
  const role = getAgentRole(filename);
  const avatar = getAgentAvatar(filename);
  const type = inferType(filename);
  const color = AGENT_TYPE_COLORS[type] ?? AGENT_TYPE_COLORS.custom;

  const displayName = nickname ?? agent?.name ?? filename.replace(/\.agent\.md$/i, "");
  const displayRole = role ?? agent?.description?.split(".")[0] ?? "Agente VS Code";

  return (
    <>
      <div className={`${styles.card} ${runningExecution ? styles.cardRunning : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
        <div className={styles.typeBadge} style={{ background: color }}>
          {type}
        </div>

        {/* Running indicator */}
        {runningExecution && (
          <div className={styles.runningBanner}>
            <span className={styles.runningPulse} />
            <span className={styles.runningText}>
              EN EJECUCIÓN{runningTicketAdoId != null ? ` · ADO-${runningTicketAdoId}` : ""}
            </span>
          </div>
        )}

        {/* Kebab menu */}
        <div className={styles.menuWrapper}>
          <button
            className={styles.kebab}
            onClick={(e) => { e.stopPropagation(); setMenuOpen((o) => !o); }}
            title="Opciones"
          >
            ⋮
          </button>
          {menuOpen && (
            <div className={styles.menu} onMouseLeave={() => setMenuOpen(false)}>
              <button onClick={() => { setMenuOpen(false); setHistoryOpen(true); }}>
                📜 Ver historial de tickets
              </button>
              <button onClick={() => { setMenuOpen(false); onEdit(filename); }}>
                ✏️ Editar empleado
              </button>
              <button
                className={styles.menuDanger}
                onClick={() => { setMenuOpen(false); removePinnedAgent(filename); onRemoved(); }}
              >
                🗑️ Quitar del equipo
              </button>
            </div>
          )}
        </div>

        {/* Avatar */}
        <div className={styles.avatarWrap}>
          <PixelAvatar value={avatar} size="lg" name={displayName} />
        </div>

        {/* Info */}
        <div className={styles.name}>{displayName}</div>
        <div className={styles.role}>{displayRole}</div>

        {/* CTA */}
        <button className={styles.assignBtn} onClick={() => setLaunchOpen(true)}>
          Asignar Ticket →
        </button>

        {/* Secondary action: history */}
        <button
          className={styles.historyBtn}
          onClick={() => setHistoryOpen(true)}
          title="Ver tickets que este agente trabajó"
        >
          Ver historial
        </button>
      </div>

      {launchOpen && (
        <AgentLaunchModal
          agent={agent ?? { name: displayName, filename, description: displayRole, system_prompt: "" }}
          avatarValue={avatar}
          onClose={() => setLaunchOpen(false)}
        />
      )}

      {historyOpen && (
        <AgentHistoryModal
          filename={filename}
          displayName={displayName}
          avatarValue={avatar}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </>
  );
}

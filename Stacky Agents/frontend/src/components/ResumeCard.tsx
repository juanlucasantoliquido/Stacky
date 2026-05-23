import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ResumeCard.module.css";

interface ResumeResponse {
  ok: boolean;
  has_activity: boolean;
  user: string;
  last_execution?: {
    id: number;
    agent_type: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
  };
  ticket?: {
    id: number;
    ado_id: number;
    title: string;
    ado_state: string | null;
    stacky_status: string | null;
  } | null;
  next_agent_suggested?: string | null;
}

function relativeMinutes(iso: string | null | undefined): string {
  if (!iso) return "";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const mins = Math.max(1, Math.round((Date.now() - ts) / 60000));
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.round(mins / 60);
  return `hace ${hours} h`;
}

const AGENT_LABEL: Record<string, string> = {
  business: "Business",
  functional: "Functional",
  technical: "Technical",
  developer: "Developer",
  qa: "QA",
};

interface Props {
  projectName?: string | null;
  onResume?: (ticketId: number, agentType: string | null) => void;
}

export default function ResumeCard({ projectName, onResume }: Props) {
  const [data, setData] = useState<ResumeResponse | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const url = projectName
      ? `/api/session/resume?project=${encodeURIComponent(projectName)}`
      : "/api/session/resume";
    api
      .get<ResumeResponse>(url)
      .then(setData)
      .catch(() => setData(null));
  }, [projectName]);

  if (!data || !data.has_activity || dismissed || !data.last_execution) return null;

  const exec = data.last_execution;
  const ticket = data.ticket;
  const next = data.next_agent_suggested;

  return (
    <div className={styles.card} role="region" aria-label="Continuar donde lo dejaste">
      <div className={styles.iconCol}>
        <span className={styles.icon} aria-hidden="true">📌</span>
      </div>
      <div className={styles.body}>
        <div className={styles.header}>
          <strong>Continuar donde lo dejaste</strong>
          <span className={styles.muted}>{relativeMinutes(exec.started_at)}</span>
        </div>
        <div className={styles.ticketLine}>
          {ticket ? (
            <>
              <span className={styles.ticketId}>T-{ticket.ado_id}</span>
              <span className={styles.ticketTitle}>{ticket.title}</span>
            </>
          ) : (
            <span className={styles.muted}>(ticket no encontrado)</span>
          )}
        </div>
        <div className={styles.metaLine}>
          Último agente: <strong>{AGENT_LABEL[exec.agent_type] ?? exec.agent_type}</strong>
          {next ? (
            <>
              {" · "}
              Próximo sugerido: <strong>{AGENT_LABEL[next] ?? next}</strong>
            </>
          ) : null}
        </div>
      </div>
      <div className={styles.actions}>
        <button
          className={styles.primaryBtn}
          onClick={() => {
            if (ticket && onResume) onResume(ticket.id, next ?? null);
          }}
          disabled={!ticket}
        >
          Continuar
        </button>
        <button
          className={styles.secondaryBtn}
          onClick={() => setDismissed(true)}
        >
          Empezar fresco
        </button>
      </div>
    </div>
  );
}

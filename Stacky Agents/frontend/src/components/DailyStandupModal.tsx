import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./DailyStandupModal.module.css";

interface StandupResponse {
  ok: boolean;
  user: string;
  generated_at: string | null;
  yesterday_tickets: { ticket_id: number; agent_runs: number }[];
  today_tickets: { ticket_id: number; agent_runs: number }[];
  pending_today_ticket_ids: number[];
  blockers: { ticket_id: number; agent_type: string; verdict?: string; error_message?: string }[];
  summary_text: string;
}

const SHOWN_KEY = "stacky.standup.lastShownDate";
const TARGET_HOUR = 9;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function shouldShow(): boolean {
  const now = new Date();
  if (now.getDay() === 0 || now.getDay() === 6) return false;
  if (now.getHours() < TARGET_HOUR) return false;
  return localStorage.getItem(SHOWN_KEY) !== todayKey();
}

export default function DailyStandupModal() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<StandupResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const tryShow = useCallback(() => {
    if (!shouldShow()) return;
    api
      .get<StandupResponse>("/api/standup/daily")
      .then((d) => {
        setData(d);
        setOpen(true);
        localStorage.setItem(SHOWN_KEY, todayKey());
      })
      .catch(() => {
        // Silent: si el backend está caído, no molestar al usuario.
      });
  }, []);

  useEffect(() => {
    tryShow();
    const interval = window.setInterval(tryShow, 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [tryShow]);

  if (!open || !data) return null;

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(data.summary_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" aria-label="Standup diario">
      <div className={styles.modal}>
        <header className={styles.header}>
          <h2 className={styles.title}>☀️ Buen día, {data.user.split("@")[0]}.</h2>
          <p className={styles.subtitle}>Tu standup está listo.</p>
        </header>
        <pre className={styles.content}>{data.summary_text}</pre>
        <footer className={styles.footer}>
          <button className={styles.primaryBtn} onClick={copyToClipboard}>
            {copied ? "✓ Copiado" : "Copiar para Teams"}
          </button>
          <button className={styles.secondaryBtn} onClick={() => setOpen(false)}>
            Cerrar
          </button>
        </footer>
      </div>
    </div>
  );
}

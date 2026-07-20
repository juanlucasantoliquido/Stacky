import { useState } from "react";
import { Bell } from "lucide-react";
import IconButton from "./ui/IconButton";
import NotificationPanel from "./NotificationPanel";
import { useActivityCenter } from "../hooks/useActivityCenter";
import styles from "./NotificationBell.module.css";

interface Props {
  /** Navegación no destructiva desde un ítem del feed (solo "ver"). */
  onNavigate?: (nav: { tab: string; executionId?: number }) => void;
}

/**
 * Plan 152 F4 — Campana en la barra superior. Es un IconButton (primitiva 138)
 * con badge de no-leídos. Abrir el panel marca todo como leído (C9): lo que
 * llegue con el panel abierto queda no-leído hasta la próxima apertura.
 */
export default function NotificationBell({ onNavigate }: Props) {
  const [open, setOpen] = useState(false);
  const { unread, groups, markRead } = useActivityCenter();

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next) markRead();
      return next;
    });
  };

  const badgeText = unread > 9 ? "9+" : String(unread);

  return (
    <div className={styles.root}>
      <IconButton
        label="Notificaciones"
        icon={<Bell size={18} aria-hidden="true" />}
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="dialog"
      />
      {unread > 0 && (
        <span className={styles.badge} aria-label={`${unread} sin leer`}>
          {badgeText}
        </span>
      )}
      {open && (
        <NotificationPanel
          groups={groups}
          onNavigate={onNavigate}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

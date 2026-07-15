/**
 * Notifica al usuario cuando una ejecución termina.
 *
 * Pieza local de C16. Se activa por opt-in vía `localStorage`:
 *   stacky.notify.sound = "true"
 *   stacky.notify.desktop = "true"  (requiere permiso del navegador)
 *
 * El backend ya emite eventos vía SSE; este módulo solo reacciona.
 */
import { shouldNotifyExecution } from "./notifierCore";

const SOUND_KEY = "stacky.notify.sound";
const DESKTOP_KEY = "stacky.notify.desktop";

let audioCtx: AudioContext | null = null;

function ensureAudio(): AudioContext | null {
  if (audioCtx) return audioCtx;
  try {
    const Ctor =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!Ctor) return null;
    audioCtx = new Ctor();
    return audioCtx;
  } catch {
    return null;
  }
}

/** Beep corto y elegante (no Mario coin). */
function playBeep(): void {
  const ctx = ensureAudio();
  if (!ctx) return;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    osc.type = "sine";
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.22);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    // ignore
  }
}

export function isSoundEnabled(): boolean {
  return localStorage.getItem(SOUND_KEY) === "true";
}

export function setSoundEnabled(enabled: boolean): void {
  localStorage.setItem(SOUND_KEY, enabled ? "true" : "false");
}

export function isDesktopEnabled(): boolean {
  return (
    localStorage.getItem(DESKTOP_KEY) === "true" &&
    typeof Notification !== "undefined" &&
    Notification.permission === "granted"
  );
}

export async function requestDesktopPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") {
    localStorage.setItem(DESKTOP_KEY, "true");
    return true;
  }
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  const granted = result === "granted";
  if (granted) localStorage.setItem(DESKTOP_KEY, "true");
  return granted;
}

/** Plan 134 F6: apagado explícito del aviso de escritorio desde la UI. */
export function setDesktopEnabled(enabled: boolean): void {
  localStorage.setItem(DESKTOP_KEY, enabled ? "true" : "false");
}

/** Plan 134 F6: beep de prueba — el click del toggle es el gesto de usuario que
 *  desbloquea el AudioContext del navegador, y de paso confirma que se oye. */
export function playTestBeep(): void {
  playBeep();
}

/** [ADICIÓN ARQUITECTO] Plan 134 F6 v2: notificación de escritorio de PRUEBA —
 *  valida el pipeline completo (permiso + render + click-para-volver) sin tener
 *  que esperar el fin de un run real. */
export function sendTestDesktopNotification(): void {
  if (!isDesktopEnabled()) return;
  try {
    const n = new Notification("Stacky · notificación de prueba", {
      body: "Así se verá el aviso de fin de run.",
      silent: true,
    });
    n.onclick = () => {
      try {
        window.focus();
        n.close();
      } catch {
        // ignore
      }
    };
    window.setTimeout(() => n.close(), 6000);
  } catch {
    // ignore
  }
}

interface FinishedPayload {
  agent_type: string;
  ticket_label?: string;
  status: "completed" | "error" | "cancelled" | "needs_review";
  /** Plan 134 F2 (v2): dedup por run — defensa en profundidad contra dobles
   *  montajes (StrictMode) y carreras. El emisor es ÚNICO: el notificador
   *  global (C3); el SSE del dock ya no notifica. */
  execution_id?: number;
}

let lastNotifiedAt = 0;
const MIN_GAP_MS = 1500; // solo fallback para payloads legacy SIN execution_id
const notifiedExecIds = new Map<number, number>();
// El beep conserva un gate corto propio: 5 fines simultáneos = 1 solo beep
// (el aviso de escritorio y el título SÍ salen uno por run).
let lastBeepAt = 0;
const BEEP_GAP_MS = 1000;

export function notifyExecutionFinished(payload: FinishedPayload): void {
  const now = Date.now();
  if (payload.execution_id != null) {
    if (!shouldNotifyExecution(payload.execution_id, now, notifiedExecIds)) return;
  } else {
    if (now - lastNotifiedAt < MIN_GAP_MS) return;
    lastNotifiedAt = now;
  }

  if (isSoundEnabled() && now - lastBeepAt >= BEEP_GAP_MS) {
    lastBeepAt = now;
    playBeep();
  }

  if (isDesktopEnabled()) {
    try {
      const verb = payload.status === "completed" ? "terminó" : payload.status;
      const title = `Stacky · agente ${payload.agent_type} ${verb}`;
      const body = payload.ticket_label ?? "Ejecución finalizada.";
      const n = new Notification(title, { body, silent: true });
      // Plan 134: click en la notificación = volver a la pestaña de Stacky.
      n.onclick = () => {
        try {
          window.focus();
          n.close();
        } catch {
          // ignore
        }
      };
      window.setTimeout(() => n.close(), 6000);
    } catch {
      // ignore
    }
  }
}

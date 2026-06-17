/**
 * Notifica al usuario cuando una ejecución termina.
 *
 * Pieza local de C16. Se activa por opt-in vía `localStorage`:
 *   stacky.notify.sound = "true"
 *   stacky.notify.desktop = "true"  (requiere permiso del navegador)
 *
 * El backend ya emite eventos vía SSE; este módulo solo reacciona.
 */

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

interface FinishedPayload {
  agent_type: string;
  ticket_label?: string;
  status: "completed" | "error" | "cancelled" | "needs_review";
}

let lastNotifiedAt = 0;
const MIN_GAP_MS = 1500;

export function notifyExecutionFinished(payload: FinishedPayload): void {
  const now = Date.now();
  if (now - lastNotifiedAt < MIN_GAP_MS) return;
  lastNotifiedAt = now;

  if (isSoundEnabled()) playBeep();

  if (isDesktopEnabled()) {
    try {
      const verb = payload.status === "completed" ? "terminó" : payload.status;
      const title = `Stacky · agente ${payload.agent_type} ${verb}`;
      const body = payload.ticket_label ?? "Ejecución finalizada.";
      const n = new Notification(title, { body, silent: true });
      window.setTimeout(() => n.close(), 6000);
    } catch {
      // ignore
    }
  }

  // Status bar flash (window icon won't change but title does).
  const originalTitle = document.title;
  document.title = "🤖 done — " + originalTitle;
  window.setTimeout(() => {
    document.title = originalTitle;
  }, 4000);
}

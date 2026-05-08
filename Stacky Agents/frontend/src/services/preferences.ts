/* ─── Stacky Agents — Preferences Service (localStorage + backend sync) ─── */

const KEYS = {
  pinnedAgents:    "stacky:pinnedAgents",
  agentAvatars:    "stacky:agentAvatars",
  agentNicknames:  "stacky:agentNicknames",
  agentRoles:      "stacky:agentRoles",
} as const;

const _API_BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:5050";
const _PREFS_URL = `${_API_BASE}/api/preferences`;

// ─── localStorage helpers ─────────────────────────────────────────────────
function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full or private-browsing — fail silently
  }
}

// ─── Backend sync ─────────────────────────────────────────────────────────
/**
 * Carga preferencias desde el backend y las hidrata en localStorage.
 * Llamar una vez al arrancar la app (en App.tsx useEffect).
 * Si el backend no está disponible, se usan los valores actuales de localStorage.
 */
export async function initPreferences(): Promise<void> {
  try {
    const res = await fetch(_PREFS_URL);
    if (!res.ok) return;
    const data = await res.json() as Record<string, unknown>;
    const mapping: [string, string][] = [
      [KEYS.pinnedAgents,   "pinnedAgents"],
      [KEYS.agentAvatars,   "agentAvatars"],
      [KEYS.agentNicknames, "agentNicknames"],
      [KEYS.agentRoles,     "agentRoles"],
    ];
    for (const [lsKey, backendKey] of mapping) {
      if (backendKey in data) {
        write(lsKey, data[backendKey]);
      }
    }
  } catch {
    // Backend offline — continuar con localStorage
  }
}

/** Persiste todas las preferencias actuales al backend (fire-and-forget). */
function _pushToBackend(): void {
  const payload = {
    pinnedAgents:   getPinnedAgents(),
    agentAvatars:   getAgentAvatars(),
    agentNicknames: getAgentNicknames(),
    agentRoles:     getAgentRoles(),
  };
  fetch(_PREFS_URL, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => { /* backend offline — no-op */ });
}

// ─── Pinned agents ────────────────────────────────────────────
export function getPinnedAgents(): string[] {
  return read<string[]>(KEYS.pinnedAgents, []);
}

export function setPinnedAgents(filenames: string[]): void {
  write(KEYS.pinnedAgents, filenames);
  _pushToBackend();
}

export function addPinnedAgent(filename: string): void {
  const current = getPinnedAgents();
  if (!current.includes(filename)) {
    write(KEYS.pinnedAgents, [...current, filename]);
    _pushToBackend();
  }
}

export function removePinnedAgent(filename: string): void {
  write(KEYS.pinnedAgents, getPinnedAgents().filter((f) => f !== filename));
  _pushToBackend();
}

// ─── Avatars ──────────────────────────────────────────────────
/** Value: gallery avatar ID (e.g. "dev-1") or base64 data-URI */
export function getAgentAvatars(): Record<string, string> {
  return read<Record<string, string>>(KEYS.agentAvatars, {});
}

export function setAgentAvatar(filename: string, avatarIdOrBase64: string): void {
  const current = getAgentAvatars();
  write(KEYS.agentAvatars, { ...current, [filename]: avatarIdOrBase64 });
  _pushToBackend();
}

export function getAgentAvatar(filename: string): string | null {
  return getAgentAvatars()[filename] ?? null;
}

// ─── Nicknames ────────────────────────────────────────────────
export function getAgentNicknames(): Record<string, string> {
  return read<Record<string, string>>(KEYS.agentNicknames, {});
}

export function setAgentNickname(filename: string, nickname: string): void {
  const current = getAgentNicknames();
  write(KEYS.agentNicknames, { ...current, [filename]: nickname });
  _pushToBackend();
}

export function getAgentNickname(filename: string): string | null {
  return getAgentNicknames()[filename] ?? null;
}

// ─── Roles ────────────────────────────────────────────────────
export function getAgentRoles(): Record<string, string> {
  return read<Record<string, string>>(KEYS.agentRoles, {});
}

export function setAgentRole(filename: string, role: string): void {
  const current = getAgentRoles();
  write(KEYS.agentRoles, { ...current, [filename]: role });
  _pushToBackend();
}

export function getAgentRole(filename: string): string | null {
  return getAgentRoles()[filename] ?? null;
}

// ─── Bulk clear (for dev / reset) ─────────────────────────────
export function clearAllPreferences(): void {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
}

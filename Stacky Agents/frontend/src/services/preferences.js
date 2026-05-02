/* ─── Stacky Agents — Preferences Service (localStorage + backend sync) ─── */
const KEYS = {
    pinnedAgents: "stacky:pinnedAgents",
    agentAvatars: "stacky:agentAvatars",
    agentNicknames: "stacky:agentNicknames",
    agentRoles: "stacky:agentRoles",
};
const _API_BASE = import.meta.env?.VITE_API_BASE ?? "http://localhost:5050";
const _PREFS_URL = `${_API_BASE}/api/preferences`;
// ─── localStorage helpers ─────────────────────────────────────────────────
function read(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    }
    catch {
        return fallback;
    }
}
function write(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    }
    catch {
        // storage full or private-browsing — fail silently
    }
}
// ─── Backend sync ─────────────────────────────────────────────────────────
/**
 * Carga preferencias desde el backend y las hidrata en localStorage.
 * Llamar una vez al arrancar la app (en App.tsx useEffect).
 * Si el backend no está disponible, se usan los valores actuales de localStorage.
 */
export async function initPreferences() {
    try {
        const res = await fetch(_PREFS_URL);
        if (!res.ok)
            return;
        const data = await res.json();
        const mapping = [
            [KEYS.pinnedAgents, "pinnedAgents"],
            [KEYS.agentAvatars, "agentAvatars"],
            [KEYS.agentNicknames, "agentNicknames"],
            [KEYS.agentRoles, "agentRoles"],
        ];
        for (const [lsKey, backendKey] of mapping) {
            if (backendKey in data) {
                write(lsKey, data[backendKey]);
            }
        }
    }
    catch {
        // Backend offline — continuar con localStorage
    }
}
/** Persiste todas las preferencias actuales al backend (fire-and-forget). */
function _pushToBackend() {
    const payload = {
        pinnedAgents: getPinnedAgents(),
        agentAvatars: getAgentAvatars(),
        agentNicknames: getAgentNicknames(),
        agentRoles: getAgentRoles(),
    };
    fetch(_PREFS_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    }).catch(() => { });
}
// ─── Pinned agents ────────────────────────────────────────────
export function getPinnedAgents() {
    return read(KEYS.pinnedAgents, []);
}
export function setPinnedAgents(filenames) {
    write(KEYS.pinnedAgents, filenames);
    _pushToBackend();
}
export function addPinnedAgent(filename) {
    const current = getPinnedAgents();
    if (!current.includes(filename)) {
        write(KEYS.pinnedAgents, [...current, filename]);
        _pushToBackend();
    }
}
export function removePinnedAgent(filename) {
    write(KEYS.pinnedAgents, getPinnedAgents().filter((f) => f !== filename));
    _pushToBackend();
}
// ─── Avatars ──────────────────────────────────────────────────
/** Value: gallery avatar ID (e.g. "dev-1") or base64 data-URI */
export function getAgentAvatars() {
    return read(KEYS.agentAvatars, {});
}
export function setAgentAvatar(filename, avatarIdOrBase64) {
    const current = getAgentAvatars();
    write(KEYS.agentAvatars, { ...current, [filename]: avatarIdOrBase64 });
    _pushToBackend();
}
export function getAgentAvatar(filename) {
    return getAgentAvatars()[filename] ?? null;
}
// ─── Nicknames ────────────────────────────────────────────────
export function getAgentNicknames() {
    return read(KEYS.agentNicknames, {});
}
export function setAgentNickname(filename, nickname) {
    const current = getAgentNicknames();
    write(KEYS.agentNicknames, { ...current, [filename]: nickname });
    _pushToBackend();
}
export function getAgentNickname(filename) {
    return getAgentNicknames()[filename] ?? null;
}
// ─── Roles ────────────────────────────────────────────────────
export function getAgentRoles() {
    return read(KEYS.agentRoles, {});
}
export function setAgentRole(filename, role) {
    const current = getAgentRoles();
    write(KEYS.agentRoles, { ...current, [filename]: role });
    _pushToBackend();
}
export function getAgentRole(filename) {
    return getAgentRoles()[filename] ?? null;
}
// ─── Bulk clear (for dev / reset) ─────────────────────────────
export function clearAllPreferences() {
    Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
}

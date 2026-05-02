const BASE = import.meta.env?.VITE_API_BASE ?? "http://localhost:5050";
export const apiBase = BASE;
async function request(path, init = {}) {
    const res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: {
            "Content-Type": "application/json",
            "X-User-Email": "dev@local",
            ...(init.headers ?? {}),
        },
    });
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return res.json();
}
export const api = {
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
    delete: (path) => request(path, { method: "DELETE" }),
};

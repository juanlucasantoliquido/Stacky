const BASE = import.meta.env?.VITE_API_BASE ?? "";
/**
 * Fetch sin lanzar excepción en 4xx/5xx — devuelve RawResponse.
 * Permite al caller manejar 409 con flujo de confirmación en vez de catch.
 */
export async function rawPost(path, body, extraHeaders = {}) {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-User-Email": "dev@local",
            ...extraHeaders,
        },
        body: JSON.stringify(body),
    });
    let data = null;
    let errorBody = null;
    const text = await res.text().catch(() => "");
    if (text) {
        try {
            const parsed = JSON.parse(text);
            if (res.ok) {
                data = parsed;
            }
            else {
                errorBody = parsed;
            }
        }
        catch {
            if (!res.ok) {
                errorBody = { message: text };
            }
        }
    }
    return { status: res.status, ok: res.ok, data, errorBody };
}
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
    put: (path, body) => request(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
    patch: (path, body) => request(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
    delete: (path, body) => request(path, { method: "DELETE", body: body ? JSON.stringify(body) : undefined }),
    /** POST con headers adicionales (ej. X-Stacky-Agent-Token para el gateway). */
    postWithHeaders: (path, body, extraHeaders) => request(path, {
        method: "POST",
        body: JSON.stringify(body),
        headers: extraHeaders,
    }),
};

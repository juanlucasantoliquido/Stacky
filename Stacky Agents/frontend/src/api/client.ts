const BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:5050";

/**
 * Respuesta estructurada del gateway que preserva el cuerpo JSON
 * incluso en status de error (4xx/5xx).
 * Usada por agentCompletion para diferenciar 409 html_already_published
 * de otros errores sin perder el error.code.
 */
export interface RawResponse<T> {
  status: number;
  ok: boolean;
  data: T | null;
  /** Error parseado del cuerpo si la respuesta no es ok. */
  errorBody: GatewayErrorBody | null;
}

export interface GatewayErrorBody {
  error?: string;    // error.code machine-readable
  message?: string;  // human-readable del backend
  correlation_id?: string;
  detail?: unknown;
}

/**
 * Fetch sin lanzar excepción en 4xx/5xx — devuelve RawResponse.
 * Permite al caller manejar 409 con flujo de confirmación en vez de catch.
 */
export async function rawPost<T>(
  path: string,
  body: unknown,
  extraHeaders: Record<string, string> = {}
): Promise<RawResponse<T>> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Email": "dev@local",
      ...extraHeaders,
    },
    body: JSON.stringify(body),
  });

  let data: T | null = null;
  let errorBody: GatewayErrorBody | null = null;

  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (res.ok) {
        data = parsed as T;
      } else {
        errorBody = parsed as GatewayErrorBody;
      }
    } catch {
      if (!res.ok) {
        errorBody = { message: text };
      }
    }
  }

  return { status: res.status, ok: res.ok, data, errorBody };
}

export const apiBase = BASE;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  /** POST con headers adicionales (ej. X-Stacky-Agent-Token para el gateway). */
  postWithHeaders: <T,>(path: string, body: unknown, extraHeaders: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
      headers: extraHeaders,
    }),
};

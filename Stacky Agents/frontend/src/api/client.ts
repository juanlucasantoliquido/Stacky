import {
  GATEWAY_DOWN_STATUSES,
  reportConnectionSuccess,
  reportConnectionFailure,
} from "../services/connectionMonitor";
// Plan 273 F4 (B-02) — el error de api.* deja de aplanar el cuerpo estructurado.
// Plan 273 F6 (B-04) — TimeoutError distingue "el servidor no respondio" de "el
// operador cancelo".
import { GatewayError, TimeoutError } from "./gatewayError";

const BASE = (import.meta as any).env?.VITE_API_BASE ?? "";

// Plan 192 F2 — instrumentacion pasiva del choke-point de red. GATEWAY_DOWN_STATUSES
// se IMPORTA del monitor (fuente unica; prohibido duplicar el Set aca — C8).
// Plan 99 F1 — exportada (antes privada). Cambio ADITIVO: la firma y el cuerpo no
// cambian. Es la definición ÚNICA de "esto fue un abort" del frontend; duplicarla
// en el fetcher del preview habría dejado dos predicados que pueden divergir.
export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}
function reportOutcome(res: Response): void {
  if (GATEWAY_DOWN_STATUSES.has(res.status)) reportConnectionFailure();
  else reportConnectionSuccess();
}

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
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...extraHeaders,
      },
      body: JSON.stringify(body),
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error
  }
  reportOutcome(res);

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

/**
 * Plan 238 F3 — gemelo de lectura de rawPost: fetch GET que NO lanza en 4xx/5xx
 * y devuelve el cuerpo parseado. Necesario para distinguir 404 feature_disabled
 * de un backend caido (api.get lanza en todo non-2xx).
 */
export async function rawGet<T>(
  path: string,
  extraHeaders: Record<string, string> = {}
): Promise<RawResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...extraHeaders,
      },
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error de red
  }
  reportOutcome(res);

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

/**
 * Plan 257 F4 — gemelo de escritura de rawGet: fetch PUT que NO lanza en
 * 4xx/5xx. Necesario para leer el mensaje del 400 de un nivel de registro
 * inválido sin parsear el texto de una excepción (api.put lanza en todo
 * non-2xx y aplana el cuerpo en `${status} ${statusText}: ${text}`).
 */
export async function rawPut<T>(
  path: string,
  body: unknown,
  extraHeaders: Record<string, string> = {}
): Promise<RawResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...extraHeaders,
      },
      body: JSON.stringify(body),
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error de red
  }
  reportOutcome(res);

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

/** Plan 273 F6 (B-04) — deadline por defecto. NO es una flag: leerla del backend
 *  requeriria la misma llamada HTTP que el deadline protege (dependencia circular:
 *  si el backend cuelga, la lectura de la flag cuelga y no hay timeout). La
 *  varianza real se cubre con el override por llamador, abajo. */
export const DEFAULT_TIMEOUT_MS = 20000;

/** Plan 273 F6 (B-04) — opciones de `request()`. Aditivo sobre RequestInit. */
export interface RequestOptions extends RequestInit {
  /** 0 = SIN LIMITE. Convencion ya usada en el repo para deadlines. */
  timeoutMs?: number;
  /** Solo para tests. Se copia el PATRON de ProbeOptions (inyeccion por opcion,
   *  sin estado global, flagHealth.ts:25-32), NO su firma: la de `probeFlagHealth`
   *  es `(path) => Promise<{ json() }>` y NO expone ok/status/statusText/text(),
   *  que es justo lo que request() usa. Tipo correcto (C16): */
  fetchImpl?: (input: string, init?: RequestInit) => Promise<Response>;
}

/** Exportada SOLO para los tests de F6 (no hay forma de inyectar fetch de otro
 *  modo). Los consumidores de produccion siguen usando `api.*`. */
export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { timeoutMs, fetchImpl, ...rest } = init;
  const deadline = timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch = fetchImpl ?? ((p: string, i?: RequestInit) => fetch(p, i));

  // El signal del llamador SIGUE valiendo: se combinan a mano en vez de depender
  // de AbortSignal.any, que puede no existir en el runtime del navegador objetivo.
  let ctl: AbortController | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  let signal = rest.signal ?? undefined;
  // El deadline se resuelve por CARRERA, no solo por abort. Razon: abortar solo
  // rechaza si la implementacion de fetch honra el signal. El `fetch` del
  // navegador lo honra, pero apoyarse SOLO en eso deja el caso "fetch trabado que
  // no responde al abort" colgado para siempre, que es exactamente el bug que esta
  // fase mata. Igual se aborta, para liberar la conexion y no dejar la request
  // viva del lado del servidor.
  let onDeadline: Promise<never> | undefined;
  if (deadline > 0) {
    ctl = new AbortController();
    const onCallerAbort = () => ctl!.abort();
    if (rest.signal) {
      if (rest.signal.aborted) ctl.abort();
      else rest.signal.addEventListener("abort", onCallerAbort, { once: true });
    }
    onDeadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        ctl!.abort();
        reject(new TimeoutError(path, deadline));
      }, deadline);
    });
    signal = ctl.signal;
  }

  let res: Response;
  try {
    const fetching = doFetch(`${BASE}${path}`, {
      ...rest,
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...(rest.headers ?? {}),
      },
    });
    res = onDeadline ? await Promise.race([fetching, onDeadline]) : await fetching;
  } catch (e) {
    // Distinguir "el operador cancelo" de "el servidor no respondio" por el flag
    // `timedOut`, NO inspeccionando el AbortError: los dos producen el mismo
    // DOMException. Confundirlos seria una regresion de UX peor que el bug.
    if (timedOut) throw new TimeoutError(path, deadline);
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error
  } finally {
    // SIEMPRE, en exito y en error: sin esto cada request deja un timer vivo hasta
    // 20s y con navegacion intensa se acumulan.
    if (timer !== undefined) clearTimeout(timer);
  }
  reportOutcome(res);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    // Plan 273 F4 (B-02): GatewayError conserva `message` BYTE A BYTE (7 sitios
    // lo parsean) y agrega status/errorBody/correlation_id como campos.
    throw new GatewayError(res.status, res.statusText, text);
  }
  return res.json() as Promise<T>;
}

/**
 * Plan 273 F6 (B-04 / C2 / C23) — los SEIS verbos que enrutan por `request()`
 * reciben `opts?: RequestOptions` como parametro OPCIONAL AL FINAL. Es aditivo y
 * retrocompatible byte a byte: ningun llamador existente cambia.
 *
 * EL ORDEN DEL SPREAD NO ES COSMETICO: `...opts` va PRIMERO para que `method`,
 * `body`, `headers` y `signal` que el verbo construye GANEN sobre cualquier cosa
 * que el llamador ponga en `opts`. Al revés, un `opts` con `method` cambiaria el
 * verbo en silencio. `timeoutMs` y `fetchImpl` viajan igual: no colisionan.
 *
 * INVARIANTE CONGELADA (plan273RequestTimeout.test.ts): todo miembro de `api` que
 * llame a `request<T>(` DEBE declarar `opts?: RequestOptions` (o `init?:`). Un
 * verbo sin canal de deadline es un timeout inescapable esperando su endpoint
 * largo — paso dos veces: C2 con `post` y C23 con `postWithHeaders`, que es el
 * verbo de `finish-work` (publica en el ADO real del operador).
 */
export const api = {
  get: <T,>(path: string, init?: RequestOptions) => request<T>(path, init),
  post: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "DELETE", body: body ? JSON.stringify(body) : undefined }),
  /** POST con headers adicionales (ej. X-Stacky-Agent-Token para el gateway). */
  postWithHeaders: <T,>(
    path: string,
    body: unknown,
    extraHeaders: Record<string, string>,
    opts?: RequestOptions,
  ) =>
    request<T>(path, {
      ...opts,
      method: "POST",
      body: JSON.stringify(body),
      headers: extraHeaders,
    }),
  /** POST cancelable (Plan 99 F1): pasa un AbortSignal a fetch. ADITIVO — `post`
   *  no se toca. `request()` hace spread del RequestInit, así que el signal viaja
   *  a fetch sin cambiar nada más. */
  postAbortable: <T,>(
    path: string,
    body: unknown,
    signal: AbortSignal,
    opts?: RequestOptions,
  ) => request<T>(path, { ...opts, method: "POST", body: JSON.stringify(body), signal }),
};

import type { GatewayErrorBody } from "./client";

/**
 * Plan 273 F4 (B-02) — error de gateway que PRESERVA el cuerpo estructurado.
 *
 * CONTRATO CONGELADO: `message` mantiene BYTE A BYTE el formato historico
 * `${status} ${statusText}: ${rawText}`. NO es cosmetica: 7 sitios de produccion
 * lo parsean (CompareWizard, ProductionFlow, SectionDoctorButton,
 * VariablesSection x2, ExecutionErrorAnalysisBlock, AgentLaunchModal) y romperlo
 * los hace tomar la rama equivocada EN SILENCIO — sin error de tipos, sin test
 * rojo, sin excepcion. plan273LegacyErrorParsers.test.ts los enumera.
 * Lo que se muestra al operador sale de `userFacingMessage()`, NO de `.message`.
 */
export class GatewayError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly rawText: string;
  readonly errorBody: GatewayErrorBody | null;

  constructor(status: number, statusText: string, rawText: string) {
    super(`${status} ${statusText}: ${rawText}`);
    this.name = "GatewayError";
    this.status = status;
    this.statusText = statusText;
    this.rawText = rawText;
    let parsed: GatewayErrorBody | null = null;
    try {
      const o = JSON.parse(rawText);
      parsed = o && typeof o === "object" ? (o as GatewayErrorBody) : null;
    } catch {
      parsed = null;
    }
    this.errorBody = parsed;
  }

  get correlationId(): string | undefined {
    return this.errorBody?.correlation_id;
  }

  get flag(): string | undefined {
    const d = this.errorBody?.detail;
    if (d && typeof d === "object" && "flag" in d) {
      const f = (d as { flag?: unknown }).flag;
      if (typeof f === "string") return f;
    }
    return undefined;
  }
}

/**
 * Plan 273 F6 (B-04) — el deadline del cliente se agoto. Es una clase propia y no
 * un AbortError porque "el servidor no respondio" y "el operador cancelo" son
 * cosas distintas para el operador, y los dos producen el mismo DOMException.
 */
export class TimeoutError extends Error {
  readonly path: string;
  readonly timeoutMs: number;

  constructor(path: string, timeoutMs: number) {
    super(`Timeout de ${timeoutMs} ms en ${path}`);
    this.name = "TimeoutError";
    this.path = path;
    this.timeoutMs = timeoutMs;
  }
}

export interface UserFacingError {
  title: string;
  detail?: string;
  correlationId?: string;
  flag?: string;
  isTimeout: boolean;
}

/** Saneamiento: descarta candidatos que no son texto para el operador. */
function sanitize(candidate: string | undefined): { text: string | null; flag?: string } {
  if (!candidate) return { text: null };
  let t = candidate;
  let flag: string | undefined;
  const m = t.match(/STACKY_[A-Z0-9_]+/);
  if (m) {
    flag = m[0];
    t = t.replace(/\s*\(?STACKY_[A-Z0-9_]+(=[a-zA-Z]+)?\)?\.?/g, "").trim();
  }
  if (/^\d{3}\s/.test(t)) return { text: null, flag };
  if (/^\s*[{[]/.test(t)) return { text: null, flag };
  if (t.includes('{"')) return { text: null, flag };
  if (!t) return { text: null, flag };
  return { text: t, flag };
}

/**
 * Mensajes con los que los navegadores reportan un FALLO DE RED en fetch.
 *
 * POR QUE EXISTE ESTA LISTA (ambiguedad del plan resuelta en la implementacion).
 * El plan define el paso 0 como "un Error que no es GatewayError ni TimeoutError
 * y cuyo message no matchea /^\d{3}\s/ => devolver e.message tal cual (es un
 * error de PROGRAMA)" y el paso 4 como "un Error comun => 'No se pudo conectar
 * con el servidor.' (fallo de red)". Tal como estan escritos **se contradicen**:
 * `new Error("Failed to fetch")` es un Error, no es GatewayError y su message no
 * empieza con tres digitos, asi que el paso 0 se lo comeria y el paso 4 nunca
 * correria — pero el plan tiene un caso de test para CADA UNO
 * (ufm_error_de_red espera la frase de red; ufm_un_typeerror espera el message
 * crudo). La clase no alcanza para distinguirlos: un fallo de fetch es un
 * TypeError y un crash de render tambien.
 * Discriminador elegido: los mensajes de red son un conjunto CERRADO y conocido
 * de los navegadores. Lo que matchea esta lista es red (paso 4); todo lo demas es
 * error de programa y se muestra tal cual (paso 0).
 */
const NETWORK_ERROR_MESSAGES = [
  "failed to fetch",        // Chrome / Edge
  "networkerror",           // Firefox: "NetworkError when attempting to fetch resource."
  "load failed",            // Safari
  "network request failed",
  "fetch failed",           // undici / Node
  "err_network",
  "err_internet_disconnected",
];

function isNetworkError(e: Error): boolean {
  const m = e.message.toLowerCase();
  return NETWORK_ERROR_MESSAGES.some((n) => m.includes(n));
}

/**
 * Plan 273 F4 (B-02) — traduce cualquier cosa lanzada al texto que ve el operador.
 * Orden de prioridad (el paso 0 es de v2/C14 y va PRIMERO):
 *  0. Error de PROGRAMA (no GatewayError, no timeout, no de red) => su message,
 *     saneado. Sin esto, un TypeError de render se mostraba como error de red y
 *     F4 EMPEORABA el unico archivo de UI que toca (PageErrorBoundary recibe
 *     crashes de render, no rechazos de api.*).
 *  1. GatewayError con errorBody.message util => esa frase (camino feliz).
 *  2. GatewayError sin message util => frase por familia de status, nunca el
 *     status crudo.
 *  3. Timeout (lo marca F6) => frase de timeout.
 *  4. Error de red => "No se pudo conectar con el servidor."
 *  5. Cualquier otra cosa => "Error inesperado."
 * El saneamiento se aplica SIEMPRE, incluido el camino del paso 0.
 */
export function userFacingMessage(e: unknown): UserFacingError {
  // Paso 3 — timeout del cliente (F6). Va antes del paso 0 porque TimeoutError ES
  // un Error y el paso 0 devolveria su message tecnico ("Timeout de 20000 ms en
  // /api/x"), que no es texto para el operador.
  if (e instanceof TimeoutError) {
    return { title: "La operación tardó más de lo esperado.", isTimeout: true };
  }
  if (e instanceof GatewayError) {
    const s = sanitize(e.errorBody?.message);
    const flag = e.flag ?? s.flag;
    if (s.text) {
      return { title: s.text, correlationId: e.correlationId, flag, isTimeout: false };
    }
    const alt = sanitize(e.errorBody?.error);
    const flag2 = flag ?? alt.flag;
    let title: string;
    if (e.status === 403 || e.status === 404) title = "Esta funcionalidad está desactivada.";
    else if (e.status === 409) title = "Ya hay una operación en curso.";
    else if (e.status >= 500) title = "El servidor tuvo un problema al procesar la solicitud.";
    else title = "No se pudo completar la operación.";
    return { title, correlationId: e.correlationId, flag: flag2, isTimeout: false };
  }
  if (e instanceof Error) {
    // Paso 4 — fallo de red.
    if (isNetworkError(e)) {
      return { title: "No se pudo conectar con el servidor.", isTimeout: false };
    }
    // Paso 0 (C14) — error de PROGRAMA: se muestra su message REAL, saneado.
    const s = sanitize(e.message);
    if (s.text) return { title: s.text, flag: s.flag, isTimeout: false };
    return { title: "Error inesperado.", flag: s.flag, isTimeout: false };
  }
  return { title: "Error inesperado.", isTimeout: false };
}

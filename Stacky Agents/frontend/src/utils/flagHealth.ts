/**
 * Veredicto del health-check de tabs opcionales (Migrador/DevOps).
 * Regla congelada (plan 135 F6): SOLO una respuesta JSON válida con
 * flag_enabled === true|false es veredicto. Cualquier otra cosa (red caída,
 * body no-JSON, JSON sin el campo) es "unknown" y NO cambia el estado previo.
 */
export type FlagHealthVerdict = "enabled" | "disabled" | "unknown";

export function interpretFlagHealthResponse(body: unknown): FlagHealthVerdict {
  if (typeof body === "object" && body !== null && "flag_enabled" in body) {
    const v = (body as { flag_enabled?: unknown }).flag_enabled;
    if (v === true) return "enabled";
    if (v === false) return "disabled";
  }
  return "unknown";
}

/** unknown conserva el último estado conocido (sticky). */
export function nextEnabledState(prev: boolean, verdict: FlagHealthVerdict): boolean {
  if (verdict === "enabled") return true;
  if (verdict === "disabled") return false;
  return prev;
}

export interface ProbeOptions {
  fetchImpl?: (path: string) => Promise<{ json(): Promise<unknown> }>;
  /** Reintentos ADICIONALES ante fallo de red/parseo/"unknown". Default 2. */
  retries?: number;
  /** Espera antes del primer reintento; se duplica en cada uno. Default 400. */
  backoffMs?: number;
  sleepImpl?: (ms: number) => Promise<void>;
}

export async function probeFlagHealth(
  path: string,
  opts: ProbeOptions = {}
): Promise<FlagHealthVerdict> {
  // fetch se invoca vía lambda para no perder el binding a window.
  const fetchImpl = opts.fetchImpl ?? ((p: string) => fetch(p));
  const retries = opts.retries ?? 2;
  const backoffMs = opts.backoffMs ?? 400;
  const sleep =
    opts.sleepImpl ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let wait = backoffMs;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetchImpl(path);
      const verdict = interpretFlagHealthResponse(await res.json());
      if (verdict !== "unknown") return verdict; // JSON válido = veredicto final
    } catch {
      // red caída o body no-JSON: cae al retry
    }
    if (attempt < retries) {
      await sleep(wait);
      wait *= 2;
    }
  }
  return "unknown";
}

/**
 * Plan 265 F2.5 — Matriz de capacidades de la consola por runtime: una sola
 * fuente de verdad. Lógica pura, sin React. Un runtime desconocido NUNCA
 * habilita nada por accidente: degrada con nota explícita.
 */

export type RuntimeId = "codex_cli" | "claude_code_cli" | "github_copilot" | "unknown";

export interface ConsoleCapability {
  supported: boolean;
  /** Texto que la UI muestra cuando `supported` es false, o cuando el soporte es
   *  parcial. `null` cuando no hay nada que aclarar. En español, para el operador. */
  note: string | null;
}

export interface ConsoleCapabilities {
  cancel: ConsoleCapability; // los 3 pueden; copilot es cooperativo
  relaunch: ConsoleCapability; // depende de que la corrida registre su origen
  modelEffortSlot: ConsoleCapability; // seam del Plan 264
  repoPanel: ConsoleCapability; // depende del workspace, no del runtime
}

const REAL_RUNTIMES: RuntimeId[] = ["codex_cli", "claude_code_cli", "github_copilot"];

/** Normaliza `metadata.runtime` (que puede venir null, vacío o con un valor futuro). */
export function normalizeRuntime(raw: unknown): RuntimeId {
  if (typeof raw === "string" && REAL_RUNTIMES.includes(raw as RuntimeId)) {
    return raw as RuntimeId;
  }
  return "unknown";
}

const CANCEL_NOTE: Record<RuntimeId, string | null> = {
  codex_cli: null,
  claude_code_cli: "Cierre ordenado: el turno en curso termina antes de salir.",
  github_copilot: "Cancelación cooperativa: el turno en curso puede tardar en cerrarse.",
  unknown: "Herramienta no reconocida: se pide la cancelación igual; puede no tener efecto inmediato.",
};

/** La matriz. Nunca lanza. Un runtime desconocido NUNCA habilita nada por
 *  accidente: degrada con nota explícita. */
export function capabilitiesFor(
  runtime: RuntimeId,
  opts: { hasOrigin: boolean },
): ConsoleCapabilities {
  const rt = normalizeRuntime(runtime);
  const hasOrigin = opts?.hasOrigin === true;
  return {
    cancel: { supported: true, note: CANCEL_NOTE[rt] },
    relaunch: hasOrigin
      ? { supported: true, note: null }
      : { supported: false, note: "No se puede volver a lanzar: esta corrida no registra su origen." },
    modelEffortSlot: { supported: false, note: "Selector de modelo y esfuerzo: pendiente del Plan 264." },
    repoPanel: { supported: true, note: null },
  };
}

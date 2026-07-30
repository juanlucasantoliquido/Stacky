/**
 * Plan 136 — Lógica pura del store workbench (higiene de proyecto F5 y
 * migración del persist F6), extraída para tests vitest sin zustand/jsdom.
 */
import type { AgentRuntime, ContextBlock } from "../types";
import type { ConsolePresentation } from "../services/consolePresentation";
import { normalizePresentation, presentationFromLegacy } from "../services/consolePresentation";

export const WORKBENCH_PERSIST_VERSION = 4;

export interface WorkbenchPersistV3 {
  agentRuntime: AgentRuntime;
  codexConsoleExecutionId: number | null;
  codexConsoleMinimized: boolean;
}

/** Plan 265 — v4 agrega la presentación de la consola. `codexConsoleMinimized`
 *  se CONSERVA y se sigue escribiendo: un deploy viejo rehidrata sin romper. */
export interface WorkbenchPersistV4 extends WorkbenchPersistV3 {
  codexConsolePresentation: ConsolePresentation;
}

const VALID_RUNTIMES: AgentRuntime[] = ["github_copilot", "codex_cli", "claude_code_cli"];

/** Migración v1/v2/v3 → v4. Preserva EXACTAMENTE el remapeo del Plan 37
 *  (copilot heredado → claude_code_cli cuando fromVersion < 2, ver
 *  workbench.ts:139-155 actual), agrega los campos de consola con defaults
 *  inertes (null/false) para todo lo anterior a v3, y deriva/lee la
 *  presentación de consola (Plan 265 F1) según la versión de origen. */
export function migrateWorkbenchPersist(
  persisted: unknown,
  fromVersion: number,
): WorkbenchPersistV4 {
  const prev = (persisted ?? {}) as {
    agentRuntime?: unknown;
    codexConsoleExecutionId?: unknown;
    codexConsoleMinimized?: unknown;
    codexConsolePresentation?: unknown;
  };
  let rt: AgentRuntime =
    typeof prev.agentRuntime === "string" &&
    VALID_RUNTIMES.includes(prev.agentRuntime as AgentRuntime)
      ? (prev.agentRuntime as AgentRuntime)
      : "claude_code_cli";
  if (fromVersion < 2 && rt === "github_copilot") rt = "claude_code_cli";
  const execId =
    fromVersion >= 3 && typeof prev.codexConsoleExecutionId === "number"
      ? prev.codexConsoleExecutionId
      : null;
  const minimized = fromVersion >= 3 && prev.codexConsoleMinimized === true;
  const presentation =
    fromVersion >= 4
      ? normalizePresentation(prev.codexConsolePresentation)
      : presentationFromLegacy(minimized); // estado v3 o anterior: se deriva del booleano
  return {
    agentRuntime: rt,
    codexConsoleExecutionId: execId,
    codexConsoleMinimized: minimized,
    codexConsolePresentation: presentation,
  };
}

export interface ProjectChangeReset {
  activeTicketId: null;
  activeExecutionId: null;
  blocks: ContextBlock[];
  chatDrawerTicketId: null;
  chatDrawerOpen: false;
}

/** F5: higiene al cambiar de proyecto. Devuelve null cuando NO hay que resetear
 *  (primera asignación al bootear, o mismo nombre de proyecto). Incluye
 *  activeExecutionId por consistencia con setActiveTicket (workbench.ts:86-87). */
export function projectChangeReset(
  prevName: string | null,
  nextName: string | null,
): ProjectChangeReset | null {
  if (prevName === null) return null; // boot: primera asignación, nada que limpiar
  if (prevName === nextName) return null; // mismo proyecto: no-op
  return {
    activeTicketId: null,
    activeExecutionId: null,
    blocks: [],
    chatDrawerTicketId: null,
    chatDrawerOpen: false,
  };
}

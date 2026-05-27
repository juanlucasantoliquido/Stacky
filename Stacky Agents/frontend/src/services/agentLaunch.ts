import { Agents } from "../api/endpoints";
import type { AgentRuntime, AgentType, ContextBlock, VsCodeAgent } from "../types";
import { getAgentType } from "./preferences";

export function inferAgentTypeFromFilename(filename: string): AgentType {
  const override = getAgentType(filename) as AgentType | null;
  if (override) return override;

  const normalized = (filename || "").toLowerCase();
  if (normalized.includes("business") || normalized.includes("negocio")) return "business";
  if (normalized.includes("functional") || normalized.includes("funcional")) return "functional";
  if (normalized.includes("technical") || normalized.includes("tecnic")) return "technical";
  if (normalized.includes("dev") || normalized.includes("desarrollador")) return "developer";
  if (normalized.includes("qa") || normalized.includes("test")) return "qa";
  return "custom";
}

export function findVsCodeAgent(
  vsCodeAgents: VsCodeAgent[],
  filename: string | null | undefined
): VsCodeAgent | null {
  if (!filename) return null;
  return vsCodeAgents.find((agent) => agent.filename === filename) ?? null;
}

export function runtimeRequiresVsCodeAgent(runtime: AgentRuntime): boolean {
  return runtime !== "github_copilot";
}

/** Runtimes CLI que streamean por SSE a la consola in-page (dock interactivo). */
export function isCliRuntime(runtime: AgentRuntime): boolean {
  return runtime === "codex_cli" || runtime === "claude_code_cli";
}

/** Extrae el execution_id del resultado de un launch, si vino. */
export function extractExecutionId(result: unknown): number | null {
  if (result && typeof result === "object" && "execution_id" in result) {
    const id = (result as { execution_id: unknown }).execution_id;
    return typeof id === "number" ? id : null;
  }
  return null;
}

/**
 * Abre la consola in-page si el runtime es CLI y el launch devolvió execution_id.
 * Centraliza la lógica que comparten TicketBoard (Run de tarjeta y run funcional
 * del epic) y AgentLaunchModal, para que ningún punto de lanzamiento descarte el
 * execution_id y deje la actividad sólo en la consola del backend.
 *
 * `openConsole` recibe el setter del store (useWorkbench.setCodexConsoleExecution);
 * se inyecta para no acoplar este servicio al store. Devuelve true si abrió el dock.
 */
export function openConsoleIfCliRuntime(
  runtime: AgentRuntime,
  result: unknown,
  openConsole: (executionId: number) => void
): boolean {
  if (!isCliRuntime(runtime)) return false;
  const executionId = extractExecutionId(result);
  if (executionId == null) return false;
  openConsole(executionId);
  return true;
}

export function launchInProgressLabel(runtime: AgentRuntime): string {
  return runtime === "github_copilot" ? "⏳ Abriendo chat…" : "⏳ Lanzando…";
}

/** Nombre legible del runtime, para badges e indicadores de lanzamiento. */
export function runtimeDisplayLabel(runtime: AgentRuntime): string {
  switch (runtime) {
    case "github_copilot":
      return "GitHub Copilot";
    case "codex_cli":
      return "Codex CLI";
    case "claude_code_cli":
      return "Claude Code CLI";
    default:
      return runtime;
  }
}

export function humanizeAgentLaunchError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");

  if (raw.includes("missing_vscode_agent_filename")) {
    return "Este runtime necesita un agente VS Code (.agent.md) seleccionado.";
  }
  if (raw.includes("not_implemented")) {
    return "Este runtime no está habilitado en este flujo.";
  }
  if (raw.includes("unknown_runtime")) {
    return "El runtime seleccionado no es válido.";
  }
  if (raw.includes("503")) {
    return "VS Code no está conectado al bridge de Stacky.";
  }
  if (raw.includes("504")) {
    return "VS Code tardó demasiado en responder. Reintentá en unos segundos.";
  }

  return raw.replace(/^Error:\s*/, "") || "No se pudo lanzar el agente.";
}

export async function launchAgentWithRuntime({
  ticketId,
  projectName,
  runtime,
  contextBlocks,
  vscodeAgent,
  modelOverride,
}: {
  ticketId: number;
  projectName?: string | null;
  runtime: AgentRuntime;
  contextBlocks: ContextBlock[];
  vscodeAgent?: VsCodeAgent | null;
  modelOverride?: string | null;
}) {
  if (runtime === "github_copilot") {
    return Agents.openChat({
      ticket_id: ticketId,
      project: projectName ?? undefined,
      context_blocks: contextBlocks,
      vscode_agent_filename: vscodeAgent?.filename ?? undefined,
      model_override: modelOverride,
    });
  }

  if (!vscodeAgent) {
    throw new Error("Seleccioná un agente VS Code antes de ejecutar con este runtime.");
  }

  const agentType = inferAgentTypeFromFilename(vscodeAgent.filename);
  const systemPrompt = (vscodeAgent.system_prompt ?? "").trim();

  if (agentType === "custom" && !systemPrompt) {
    throw new Error(
      "El agente seleccionado no expone system prompt. Abrilo en GitHub Copilot o elegí otro agente."
    );
  }

  return Agents.runWithOptions({
    agent_type: agentType,
    ticket_id: ticketId,
    project: projectName ?? undefined,
    context_blocks: contextBlocks,
    runtime,
    vscode_agent_filename: vscodeAgent.filename,
    model_override: modelOverride,
    ...(agentType === "custom" ? { system_prompt_override: systemPrompt } : {}),
  });
}

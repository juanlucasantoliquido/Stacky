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

export function launchInProgressLabel(runtime: AgentRuntime): string {
  return runtime === "github_copilot" ? "⏳ Abriendo chat…" : "⏳ Lanzando…";
}

export function humanizeAgentLaunchError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");

  if (raw.includes("missing_vscode_agent_filename")) {
    return "Este runtime necesita un agente VS Code (.agent.md) seleccionado.";
  }
  if (raw.includes("not_implemented")) {
    return "Claude Code CLI todavía no está habilitado en este flujo.";
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

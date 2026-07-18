// Plan 189 — Semáforo de rollback y simulacro read-only. Helpers PUROS (sin JSX,
// sin red, sin efectos): la UI de DeploymentsSection.tsx los consume para pintar
// el badge de reversibilidad y el modal del simulacro. Contrato espejado del
// backend services/rollback_readiness.py (SCHEMA_VERSION "189.1").

export interface Readiness {
  ready: boolean;
  to_version: string | null;
  candidates: string[];
  current_version: string | null;
  protected: boolean;
  locked: boolean;
  reasons: string[];
}

export interface SimulatedStep {
  name: string;
  command: string;
  read_only?: boolean;
  housekeeping?: boolean;
}

export interface SimulatedPlan {
  schema_version?: string;
  to_version?: string;
  smoke_timeout_s?: number;
  steps: SimulatedStep[];
  simulated?: boolean;
}

// Traducción de los códigos de razón tipados del backend (la UI nunca inventa
// texto: si aparece un código desconocido, se muestra crudo).
export const REASON_LABELS: Record<string, string> = {
  sin_target_cfg: "destino sin configurar",
  sin_versiones_retenidas: "no hay versiones retenidas",
  solo_version_actual: "solo está retenida la versión actual",
  run_en_curso: "hay un run en curso",
};

export function readinessBadge(
  r: Readiness | undefined,
): { tone: "ok" | "off" | "none"; text: string; title: string } {
  if (!r) return { tone: "none", text: "", title: "" };
  if (r.ready) {
    return {
      tone: "ok",
      text: `↩ Rollback listo → ${r.to_version}`,
      title: r.protected ? "Destino protegido: pedirá confirmación extra" : "",
    };
  }
  const motivos = r.reasons.map((x) => REASON_LABELS[x] ?? x).join("; ");
  return { tone: "off", text: "↩ Sin rollback disponible", title: motivos };
}

export function stepRows(
  plan: { steps: SimulatedStep[] } | null,
): Array<{ name: string; command: string; tags: string[] }> {
  if (!plan) return [];
  return plan.steps.map((s) => ({
    name: s.name,
    command: s.command,
    tags: [s.read_only ? "solo lectura" : "", s.housekeeping ? "housekeeping" : ""].filter(Boolean),
  }));
}

// Texto plano para "Copiar comandos": una línea por step, sin tags. `null` → ''.
export function commandsClipboardText(plan: { steps: Array<{ command: string }> } | null): string {
  if (!plan) return "";
  return plan.steps.map((s) => s.command).join("\n");
}

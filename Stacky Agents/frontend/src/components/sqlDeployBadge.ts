// Plan 200 R2/F4 — Aviso de "acá hay SQL para desplegar".
//
// El detector del backend es determinista y explicable (un `.sql` adjunto ⇒
// "alta"; solo palabras clave ⇒ "posible"). Estos helpers traducen eso a algo
// que el operador ve sin abrir el detalle.

export interface DeployNeed {
  requires: boolean;
  confidence: "alta" | "posible" | "no";
  scripts: { name: string; sha256: string; source: string }[];
  suggested_environments: string[];
  reason: string;
}

export function badge(need: DeployNeed): { show: boolean; tone: "warn" | "info"; text: string } {
  if (!need?.requires) return { show: false, tone: "info", text: "" };
  // "posible" en tono warn haría que el operador deje de mirar los warn: la
  // sospecha y la certeza no pueden verse igual.
  return need.confidence === "alta"
    ? {
        show: true,
        tone: "warn",
        text: `Despliegue SQL requerido — ${(need.scripts ?? []).length} script(s)`,
      }
    : { show: true, tone: "info", text: "Posible despliegue SQL (revisar)" };
}

export function scriptsSummary(need: DeployNeed): string {
  if (!need?.requires) return "";
  const nombres = (need.scripts ?? []).map((s) => s.name).filter(Boolean);
  if (!nombres.length) return "";
  const ambientes = (need.suggested_environments ?? []).filter(Boolean);
  return ambientes.length
    ? `${nombres.join(", ")} en ${ambientes.join(", ")}`
    : nombres.join(", ");
}

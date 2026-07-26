// Plan 216 F2/F3 — Lógica pura de la pestaña Estados.
//
// Todo lo que tiene que ver con estados del tracker vivía en dos lugares: las
// reglas estado→agente en la pestaña "Flujo", y la máquina de estados dentro
// del formulario del perfil. Eran el mismo dominio partido al medio, y nada
// avisaba cuando se contradecían.

export type StateRole = "functional" | "technical" | "developer";

export const STATE_ROLES: StateRole[] = ["functional", "technical", "developer"];

export const ROLE_LABEL: Record<StateRole, string> = {
  functional: "Analista Funcional",
  technical: "Analista Técnico",
  developer: "Desarrollador",
};

export interface RoleStateMachine {
  input_states?: string[];
  next_state_ok?: string;
  blocked_state?: string;
}

export interface FlowRule {
  id: string;
  ado_state: string;
  agent_type: string;
}

/** El valor guardado sigue siendo elegible aunque el tracker ya no lo liste:
 *  si no, abrir el dropdown le borraría al operador algo que sí configuró. */
export function optionsWithCurrent(
  options: string[] | null | undefined,
  current: string | null | undefined
): string[] {
  const lista = options ?? [];
  if (!current || lista.includes(current)) return lista;
  return [current, ...lista];
}

/**
 * Estados que una regla de flujo manda a un rol, pero que ese rol no declara
 * como `input_states`. Es una incoherencia real: el agente se lanzaría sobre un
 * estado que su propia configuración dice que no atiende.
 *
 * NO es bloqueante — se muestra y se ofrece corregir con un click.
 */
export function incoherentStatesFor(
  role: StateRole,
  rules: FlowRule[] | null | undefined,
  machine: RoleStateMachine | null | undefined
): string[] {
  const declarados = new Set(
    (machine?.input_states ?? []).map((s) => s.trim().toLowerCase())
  );
  const desdeReglas = (rules ?? [])
    .filter((r) => r.agent_type === role && r.ado_state)
    .map((r) => r.ado_state);

  const faltantes: string[] = [];
  const vistos = new Set<string>();
  for (const estado of desdeReglas) {
    const clave = estado.trim().toLowerCase();
    if (declarados.has(clave) || vistos.has(clave)) continue;
    vistos.add(clave);
    faltantes.push(estado);
  }
  return faltantes;
}

/** Cómo quedaría `input_states` al aceptar la corrección. No muta el original. */
export function withStatesAdded(
  machine: RoleStateMachine | null | undefined,
  estados: string[]
): RoleStateMachine {
  const actuales = [...(machine?.input_states ?? [])];
  const conocidos = new Set(actuales.map((s) => s.trim().toLowerCase()));
  for (const e of estados) {
    if (!conocidos.has(e.trim().toLowerCase())) {
      actuales.push(e);
      conocidos.add(e.trim().toLowerCase());
    }
  }
  return { ...(machine ?? {}), input_states: actuales };
}

export function coherenceMessage(faltantes: string[]): string | null {
  if (!faltantes.length) return null;
  const lista = faltantes.join(", ");
  return faltantes.length === 1
    ? `Hay una regla que manda "${lista}" a este rol, pero el rol no lo declara como estado de entrada.`
    : `Hay reglas que mandan ${lista} a este rol, pero el rol no los declara como estados de entrada.`;
}

/** Un rol sin `next_state_ok` no puede cerrar el ticket al terminar bien. */
export function missingRequiredFields(machine: RoleStateMachine | null | undefined): string[] {
  const faltan: string[] = [];
  if (!(machine?.input_states ?? []).length) faltan.push("estados de entrada");
  if (!(machine?.next_state_ok ?? "").trim()) faltan.push("estado al terminar OK");
  return faltan;
}

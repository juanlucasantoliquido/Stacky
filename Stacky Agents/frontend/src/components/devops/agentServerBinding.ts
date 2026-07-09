/**
 * agentServerBinding.ts — Plan 108 F4/F6
 *
 * Lógica PURA (sin React) que decide, a partir del health del panel DevOps y
 * el servidor seleccionado, si el chat del agente DevOps / el plan-apply de
 * Ambientes deben anclarse al servidor remoto. Reusada IDÉNTICA por
 * DevOpsAgentSection (F4) y EnvironmentsSection (F6) — cero lógica duplicada.
 *
 * Sin servidor seleccionado, o con cualquiera de las 3 flags OFF, el anclaje
 * NO se envía (byte-compat / cero trabajo extra al operador): el operador ve
 * un aviso (`hint`) en vez de que el agente opere en local sin que se note.
 */

export interface AgentServerBinding {
  /** Alias a incluir en el POST (server_alias), o null si no corresponde anclar. */
  sendAlias: string | null;
  /** Texto del badge "Ejecutando EN <alias>", o null si no se muestra. */
  badge: string | null;
  /** Aviso si hay servidor seleccionado pero falta alguna flag para anclar. */
  hint: string | null;
}

export interface AgentServerBindingHealth {
  remote_target_enabled?: boolean;
  servers_enabled?: boolean;
  remote_console_enabled?: boolean;
}

export interface AgentServerBindingSelectedServer {
  alias: string;
  host: string;
}

export function resolveAgentServerBinding(
  health: AgentServerBindingHealth,
  selectedServer: AgentServerBindingSelectedServer | null | undefined,
): AgentServerBinding {
  if (!selectedServer) return { sendAlias: null, badge: null, hint: null };
  const ready =
    health.remote_target_enabled === true &&
    health.servers_enabled === true &&
    health.remote_console_enabled === true;
  if (!ready) {
    return {
      sendAlias: null,
      badge: null,
      hint:
        `Servidor "${selectedServer.alias}" seleccionado, pero el agente operará LOCAL: ` +
        `activá "Operar en el servidor seleccionado" (y Servidores + Consola remota) en el Arnés.`,
    };
  }
  return {
    sendAlias: selectedServer.alias,
    badge: `Ejecutando EN ${selectedServer.alias} (${selectedServer.host})`,
    hint: null,
  };
}

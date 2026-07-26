// Plan 200 R3/R4 — Lógica pura del panel de ejecución SQL.
//
// Todo lo que decide qué se puede ejecutar y qué ya se ejecutó vive acá, puro y
// determinista: es lo único de esta capacidad que se puede testear sin una base
// de datos de por medio, y es donde un error se paga caro.

export interface EnvOption {
  alias: string;
  engine: string;
  exec_allowed: boolean;
  has_password: boolean;
}

export interface ScriptRef {
  source: "incident_attachment" | "ticket_output";
  sha256: string;
  name: string;
  incident_id?: string;
  ticket_ref?: string;
}

export interface LedgerEntry {
  alias: string;
  ticket_ref: string | null;
  script_sha256: string;
  result_ok: boolean;
  rows_affected: number | null;
  dry_run: boolean;
  executed_at: string;
  executed_by: string;
  error: string | null;
}

/**
 * Ambientes a los que SÍ se les puede escribir: registrados, con el opt-in de
 * escritura encendido y con credencial. Ofrecer uno sin password sería ofrecer
 * un botón que siempre falla.
 */
export function executableEnvs(envs: EnvOption[]): EnvOption[] {
  return (envs ?? [])
    .filter((e) => e && e.exec_allowed && e.has_password)
    .slice()
    .sort((a, b) => a.alias.localeCompare(b.alias));
}

/** Las entradas de un (alias, sha), de la más reciente a la más vieja. */
function historial(entries: LedgerEntry[], alias: string, sha: string): LedgerEntry[] {
  return (entries ?? [])
    .filter((e) => e && e.alias === alias && e.script_sha256 === sha)
    .slice()
    .sort((a, b) => String(b.executed_at ?? "").localeCompare(String(a.executed_at ?? "")));
}

function soloFecha(iso: string | null | undefined): string {
  return String(iso ?? "").slice(0, 19).replace("T", " ");
}

/** Aviso antes de repetir algo que ya se aplicó. Vacío si no hay nada que avisar. */
export function idempotencyWarning(entries: LedgerEntry[], alias: string, sha: string): string {
  const previa = historial(entries, alias, sha).find((e) => e.result_ok && !e.dry_run);
  return previa ? `Ya ejecutado el ${soloFecha(previa.executed_at)}` : "";
}

export function ledgerRow(e: LedgerEntry): string {
  const partes = [
    soloFecha(e.executed_at),
    e.alias,
    e.dry_run ? "DRY-RUN" : e.result_ok ? "OK" : "FALLO",
  ];
  if (e.rows_affected != null) partes.push(`${e.rows_affected} filas`);
  return partes.join(" · ");
}

export type DeployState = "aplicado" | "fallo" | "no-registrado";

/**
 * Dónde está parado un script en un ambiente, según la bitácora.
 *
 * Manda el intento MÁS RECIENTE: si falló, después se arregló y se volvió a
 * correr bien, el estado es "aplicado"; si el último intento falló, decir
 * "aplicado" porque hubo un ok viejo sería mentir sobre el estado actual.
 *
 * Un dry-run no cambia el estado: no tocó nada.
 */
export function deployStatus(
  entries: LedgerEntry[],
  alias: string,
  sha: string,
): { state: DeployState; detail: string } {
  const reales = historial(entries, alias, sha).filter((e) => !e.dry_run);
  if (!reales.length) return { state: "no-registrado", detail: "Sin registro en este ambiente" };

  const ultima = reales[0];
  const fecha = soloFecha(ultima.executed_at);
  return ultima.result_ok
    ? { state: "aplicado", detail: `aplicado (${fecha})` }
    : { state: "fallo", detail: `fallo (${fecha})` };
}

export function deployStatusByEnv(
  entries: LedgerEntry[],
  aliases: string[],
  sha: string,
): Record<string, DeployState> {
  const salida: Record<string, DeployState> = {};
  for (const alias of aliases ?? []) {
    salida[alias] = deployStatus(entries, alias, sha).state;
  }
  return salida;
}

/**
 * sha256 del texto mostrado, para comprobar que lo que se ve es lo que se va a
 * ejecutar. El backend igual re-lee y re-valida: esto es la verificación del
 * lado del operador, no la que protege la base.
 */
export async function sha256Hex(text: string): Promise<string> {
  const datos = new TextEncoder().encode(text ?? "");
  const buffer = await crypto.subtle.digest("SHA-256", datos);
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

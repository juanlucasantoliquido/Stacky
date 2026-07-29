// Plan 267 F4 — Ejecutor UNICO de acciones DevOps.
//
// La confirmacion se DERIVA del catalogo, no se escribe a mano en cada seccion.
// Reusa confirmGateway (services/confirmGateway.ts) tal cual: mismo
// ConfirmRequest, mismo ConfirmFn, mismo denyByDefault. PROHIBIDO crear un
// segundo mecanismo de confirmacion.
import type { ConfirmFn, ConfirmRequest } from './confirmGateway';
import type { DevOpsActionMeta } from './devopsActionTypes';

export interface DevOpsActionReceipt {
  actionId: string;
  ok: boolean;
  summary: string;
  detail: string;
  navPath: string;
  startedAt: number;
  finishedAt: number;
  /** false = el operador dijo que no, o no habia gateway cableado. */
  confirmed: boolean;
  /** F7 — payload crudo que devolvio el binding (p.ej. build_id, pipeline_id,
   *  stdout). Ausente si el binding no devolvio nada o la accion no llego a
   *  ejecutarse. Las secciones recableadas lo usan para conservar el mismo
   *  seguimiento (polling, links) que tenian antes de F7. */
  data?: unknown;
}

export interface DevOpsActionRunContext {
  askConfirm: ConfirmFn;
  navigate: (path: string) => void;
  now: () => number; // inyectable => testeable sin fake timers
  onReceipt?: (r: DevOpsActionReceipt) => void;
}

export interface DevOpsActionBinding {
  id: string;
  run: (
    params: Record<string, string>,
    ctx: DevOpsActionRunContext
  ) => Promise<{ ok: boolean; summary: string; detail?: string; data?: unknown }>;
}

export const IMPACT_TEXT: Record<string, string> = {
  none: 'Sin impacto',
  low: 'Impacto bajo',
  high: 'Impacto alto',
};

/** null si effect === 'read': NO se molesta al operador para leer.
 *  tone 'danger' <=> impact 'high'. El mensaje SIEMPRE nombra los 4 datos que
 *  el operador pidio ver: accion, entorno, impacto y que va a pasar. */
export function confirmRequestFor(
  a: DevOpsActionMeta,
  params: Record<string, string>
): ConfirmRequest | null {
  if (a.effect === 'read') return null;
  const env = a.targets_environment
    ? (params.environment || 'sin entorno declarado')
    : '';
  const donde = env ? ` sobre el entorno ${env}` : '';
  return {
    title: a.label,
    message: `${a.summary}${donde}. ${IMPACT_TEXT[a.impact]}. Esta acción escribe en un sistema real y no se puede deshacer sola.`,
    confirmLabel: a.label,
    tone: a.impact === 'high' ? 'danger' : 'default',
  };
}

/** Faltan params required => lista de nombres. Vacia = se puede correr. */
export function missingRequired(
  a: DevOpsActionMeta,
  params: Record<string, string>
): string[] {
  return a.params
    .filter((p) => p.required && !String(params[p.name] ?? '').trim())
    .map((p) => p.name);
}

/** v2 [C20] — El v1 le prometia por escrito al operador que «Ver en el panel te
 *  deja en la seccion CON LOS DATOS YA CARGADOS», y el unico mecanismo que
 *  tenia era ctx.navigate(a.nav_path), que va a /devops/<seccion> pelado. Era
 *  una promesa que el codigo no cumplia. Esto la cumple: query string
 *  determinista, claves ordenadas alfabeticamente (para que el test compare
 *  strings), valores vacios omitidos, y encodeURIComponent en clave y valor. */
export function navPathWithParams(
  a: DevOpsActionMeta,
  params: Record<string, string>
): string {
  const src = params ?? {};
  const pairs = Object.keys(src)
    .sort()
    .filter((k) => String(src[k] ?? '').trim())
    .map(
      (k) =>
        `${encodeURIComponent(k)}=${encodeURIComponent(String(src[k]).trim())}`
    );
  return pairs.length ? `${a.nav_path}?${pairs.join('&')}` : a.nav_path;
}

/** v3 [C22] — la paleta puede EJECUTAR esta accion, o solo llevar a su seccion.
 *
 *  EL CHEQUEO DE `effect` VA PRIMERO, Y NO ES REDUNDANTE. `reach` llega por HTTP
 *  desde GET /api/devops/actions/catalog. Los ratchets de I-REACH (F8 backend
 *  test 11, F8 frontend test 7) leen el .py del BACKEND — dos de ellos con una
 *  regex sobre el texto fuente — asi que NINGUNO observa el payload que este
 *  codigo consume. Un backend viejo contra un frontend nuevo, un proxy, o un
 *  reach editado a mano reabren el agujero con los tres tests en VERDE.
 *
 *  Misma disciplina que denyByDefault: no confiar en que el otro lado se porto
 *  bien. Una escritura NUNCA se ejecuta desde la paleta, diga lo que diga el
 *  payload. */
export function paletteMode(a: DevOpsActionMeta): 'run' | 'nav' | 'hidden' {
  if (a.effect === 'write') {
    return a.reach.includes('palette-nav') || a.reach.includes('palette-run')
      ? 'nav'
      : 'hidden';
  }
  if (a.reach.includes('palette-run')) return 'run';
  if (a.reach.includes('palette-nav')) return 'nav';
  return 'hidden';
}

/** Ejecuta. NUNCA lanza: siempre devuelve un recibo.
 *  Orden EXACTO e inviolable:
 *    1. binding ausente        -> recibo ok:false, NO se ejecuta nada
 *    2. params required faltan -> recibo ok:false, NO se confirma ni se ejecuta
 *    3. confirmRequestFor != null -> askConfirm; si devuelve false -> recibo
 *       ok:false confirmed:false y el binding NO se llama
 *    4. binding.run(...)       -> recibo con su resultado
 *    5. si run() lanza         -> recibo ok:false con el mensaje del error */
export async function runDevOpsAction(
  action: DevOpsActionMeta,
  params: Record<string, string>,
  binding: DevOpsActionBinding | undefined,
  ctx: DevOpsActionRunContext
): Promise<DevOpsActionReceipt> {
  const startedAt = ctx.now();
  const emit = (
    r: Omit<DevOpsActionReceipt, 'actionId' | 'navPath' | 'startedAt' | 'finishedAt'>
  ): DevOpsActionReceipt => {
    const receipt: DevOpsActionReceipt = {
      actionId: action.id,
      navPath: navPathWithParams(action, params),
      startedAt,
      finishedAt: ctx.now(),
      ...r,
    };
    ctx.onReceipt?.(receipt);
    return receipt;
  };

  // 1 — binding ausente.
  if (!binding) {
    return emit({
      ok: false,
      confirmed: false,
      summary: 'No hay forma de ejecutar esta acción',
      detail: `La acción ${action.id} no tiene una implementación cableada.`,
    });
  }

  // 2 — params required faltantes.
  const faltan = missingRequired(action, params);
  if (faltan.length) {
    return emit({
      ok: false,
      confirmed: false,
      summary: 'Faltan datos obligatorios',
      detail: `Sin estos valores no se puede seguir: ${faltan.join(', ')}.`,
    });
  }

  // 3 — confirmacion humana. denyByDefault niega, y eso alcanza para no ejecutar.
  const req = confirmRequestFor(action, params);
  if (req) {
    let ok = false;
    try {
      ok = await ctx.askConfirm(req);
    } catch {
      ok = false;
    }
    if (!ok) {
      return emit({
        ok: false,
        confirmed: false,
        summary: 'Cancelado por el operador',
        detail: 'No se ejecutó nada.',
      });
    }
  }

  // 4 y 5 — ejecucion.
  try {
    const res = await binding.run(params, ctx);
    return emit({
      ok: res.ok,
      confirmed: true,
      summary: res.summary,
      detail: res.detail ?? '',
      data: res.data,
    });
  } catch (e) {
    return emit({
      ok: false,
      confirmed: true,
      summary: 'La acción falló',
      detail: e instanceof Error ? e.message : String(e),
    });
  }
}

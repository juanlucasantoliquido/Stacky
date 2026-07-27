/**
 * publishChain.ts — Plan 102 F1.
 *
 * Orquestador PURO de la cadena materializar → commit → trigger.
 *
 * Tres invariantes duras:
 *
 * 1. **Corte honesto, CERO rollback.** No existe —ni puede existir— ninguna
 *    dependencia que deshaga: un commit pusheado y un pipeline disparado no se
 *    "desdisparan". Si un paso falla, la cadena PARA y reporta hasta dónde llegó.
 * 2. **No bifurca por proveedor.** Ni siquiera recibe el target: no puede
 *    discriminar aunque quisiera. El commit a Azure DevOps es real desde el Plan
 *    95 F1.a (`ado_provider.py:146`). Si el commit falla, falla el paso y se
 *    muestra el error real del endpoint.
 * 3. **Nunca afirma una certeza que no tiene.** Si el commit falla, no se sabe si
 *    el backend alcanzó a escribir en el repo: se devuelve `commitUncertain` y
 *    NUNCA se dice "no se commiteó nada".
 */

export type ChainStep = 'materialize' | 'commit' | 'trigger';
export type StepState = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface ChainProgress {
  step: ChainStep;
  state: StepState;
  detail?: string;
}

export interface ChainDeps {
  /** SOLO-LECTURA: preset + catálogo → spec. */
  materialize: () => Promise<{ spec: object; resolved: string[]; unknown_processes: string[] }>;
  /** Commit HITL al repo. Devuelve el branch efectivo si el backend lo informa. */
  commit: (spec: object, branch: string) => Promise<{ branch?: string }>;
  /** Dispara el pipeline sobre el ref dado. */
  trigger: (ref: string) => Promise<{ pipeline_id?: string; web_url?: string }>;
  /**
   * Plan 93 — gancho declarado pero DELIBERADAMENTE NO CABLEADO (C5).
   * El PreflightPanel es informativo y NUNCA bloquea (PreflightPanel.tsx:3-4:
   * "SOLO-LECTURA... el operador decide"). Cablear un veto automático acá
   * violaría el human-in-the-loop de ese plan. Se deja en el tipo para que
   * quede escrito por qué no se usa, no como pendiente.
   */
  beforeCommit?: never;
}

export type ChainOutcome =
  | {
      kind: 'completed';
      branch: string;
      pipelineId: string | null;
      webUrl: string | null;
    }
  | {
      kind: 'failed';
      failedAt: ChainStep;
      error: string;
      /** Solo en `failedAt === 'commit'`: no se sabe si el repo quedó escrito. */
      commitUncertain?: true;
      /** Solo en `failedAt === 'trigger'`: el commit SÍ salió, en este branch. */
      branch?: string;
    }
  | { kind: 'aborted_stale' };

const msg = (e: unknown): string =>
  e instanceof Error ? e.message : 'Error desconocido';

/**
 * Corre la cadena completa.
 *
 * @param expectedSpecJson `JSON.stringify` del spec que el operador VIO en el
 *   resumen. Si al materializar sale otro, la cadena aborta con `aborted_stale`
 *   en vez de publicar algo que nadie confirmó. Es la protección anti-stale:
 *   entre que se abrió el modal y se apretó confirmar, el catálogo o el preset
 *   pudieron cambiar.
 */
export async function runPublishChain(
  deps: ChainDeps,
  expectedSpecJson: string,
  branch: string,
  onProgress: (p: ChainProgress) => void,
): Promise<ChainOutcome> {
  // ── materialize ────────────────────────────────────────────────────────────
  onProgress({ step: 'materialize', state: 'running' });
  let spec: object;
  try {
    const res = await deps.materialize();
    spec = res.spec;
  } catch (e: unknown) {
    onProgress({ step: 'materialize', state: 'failed', detail: msg(e) });
    return { kind: 'failed', failedAt: 'materialize', error: msg(e) };
  }

  if (JSON.stringify(spec) !== expectedSpecJson) {
    // Nada se escribió todavía: abortar acá es gratis y es lo correcto.
    onProgress({ step: 'materialize', state: 'failed', detail: 'el resumen quedó viejo' });
    return { kind: 'aborted_stale' };
  }
  onProgress({ step: 'materialize', state: 'done' });

  // ── commit (primer side effect externo) ────────────────────────────────────
  onProgress({ step: 'commit', state: 'running' });
  let efectivo = branch;
  try {
    const res = await deps.commit(spec, branch);
    if (res?.branch) efectivo = res.branch;
  } catch (e: unknown) {
    onProgress({ step: 'commit', state: 'failed', detail: msg(e) });
    // C8 — el backend pudo fallar ANTES o DESPUÉS de escribir. No se sabe.
    return {
      kind: 'failed',
      failedAt: 'commit',
      error: msg(e),
      commitUncertain: true,
    };
  }
  onProgress({ step: 'commit', state: 'done', detail: efectivo });

  // ── trigger (segundo side effect externo) ──────────────────────────────────
  onProgress({ step: 'trigger', state: 'running' });
  try {
    const res = await deps.trigger(efectivo);
    onProgress({ step: 'trigger', state: 'done' });
    return {
      kind: 'completed',
      branch: efectivo,
      pipelineId: res?.pipeline_id ?? null,
      webUrl: res?.web_url ?? null,
    };
  } catch (e: unknown) {
    onProgress({ step: 'trigger', state: 'failed', detail: msg(e) });
    // Acá SÍ hay certeza: el commit salió. Se informa el branch para que el
    // operador pueda disparar a mano desde Trigger CI.
    return { kind: 'failed', failedAt: 'trigger', error: msg(e), branch: efectivo };
  }
}

/** Mensaje para el operador. Nunca afirma lo que no se sabe (C8). */
export function describeOutcome(o: ChainOutcome): string {
  switch (o.kind) {
    case 'completed':
      return `Publicado en ${o.branch} y pipeline disparado.`;
    case 'aborted_stale':
      return 'El resumen quedó viejo (el preset o el catálogo cambiaron). Reabrí el resumen y revisalo antes de publicar.';
    case 'failed':
      if (o.failedAt === 'materialize') return `No se pudo armar el pipeline: ${o.error}`;
      if (o.failedAt === 'commit') {
        return `El commit falló; verificá el repo antes de reintentar: ${o.error}`;
      }
      return `Quedó commiteado en ${o.branch} pero NO se disparó. Podés dispararlo desde Trigger CI. Detalle: ${o.error}`;
  }
}

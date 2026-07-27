/**
 * profileKeys.ts — Plan 98 F5.
 *
 * ÚNICO punto de escritura de las keys `devops_*` del client-profile.
 *
 * Con la flag `STACKY_DEVOPS_BOOTSTRAP_ENABLED` ON (default hoy, config.py:1565):
 *   1 PATCH chico; el merge lo hace el backend bajo lock de proceso
 *   (api/client_profile.py:323-347) ⇒ imposible pisar OTRAS keys del perfil.
 * Con la flag OFF:
 *   riel GET → merge → PUT actual, byte-idéntico al de antes de este plan.
 *
 * NO cubre `process_catalog`: no está en `PATCHABLE_PROFILE_KEYS`
 * (services/client_profile_keys.py) a propósito, porque su error de validación es
 * estructurado. `handleAutoDetect` sigue usando el PUT full por eso.
 */
import { api } from '../api/client';
import { mergeKeysIntoProfile } from './presetsModel';

export type PatchableProfileKey =
  | 'devops_pipeline_drafts'
  | 'devops_publication_presets'
  | 'devops_publication_settings'
  | 'devops_environment_settings';

/**
 * Persiste UNA key del client-profile.
 *
 * @param bootstrapEnabled `ctx.health.bootstrap_enabled === true`. Se pasa explícito
 *   (no se lee de un singleton) para que el módulo sea puro y testeable, y para que
 *   apagar la flag por UI vuelva al riel viejo sin recargar la página.
 */
export async function saveProfileKey(
  project: string,
  key: PatchableProfileKey,
  value: unknown,
  bootstrapEnabled: boolean,
): Promise<void> {
  const proj = encodeURIComponent(project);
  if (bootstrapEnabled) {
    await api.patch(`/api/projects/${proj}/client-profile/keys/${key}`, { value });
    return;
  }
  const json = await api.get<{ profile?: Record<string, unknown> }>(
    `/api/projects/${proj}/client-profile`,
  );
  const base = json.profile ?? {};
  const merged = mergeKeysIntoProfile(base, { [key]: value });
  await api.put(`/api/projects/${proj}/client-profile`, { profile: merged });
}

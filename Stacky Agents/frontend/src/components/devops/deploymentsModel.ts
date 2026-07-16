/**
 * deploymentsModel.ts — Plan 120 F7. Helpers PUROS de la sección Despliegues
 * (testeables sin render — patrón de la casa, planes 99/103/116-C3).
 */

export interface DeployTargetConfig {
  install_path: string;
  smoke: { kind: 'http' | 'ps' | 'none'; url: string | null; command: string | null };
  pre_switch: string | null;
  post_switch: string | null;
  protected: boolean;
}

export interface DeployApp {
  id: string;
  name?: string;
  artifact: { kind: 'folder' | 'zip'; path: string };
  targets: Record<string, DeployTargetConfig>;
}

export interface DeployStep {
  name: string;
  command: string | null;
  ok?: boolean;
  ms?: number;
  detail?: string;
  read_only: boolean;
  housekeeping: boolean;
}

export interface LedgerEntry {
  run_id: string;
  app_id: string;
  target: string;
  action: 'deploy' | 'rollback';
  version_id: string;
  prev_version_id?: string | null;
  status: 'running' | 'success' | 'failed' | 'failed_smoke';
  effective_status?: string;
  steps: { name: string; ok: boolean; ms: number; detail: string }[];
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface DoraMetrics {
  deploys_7d: number;
  deploys_30d: number;
  change_failure_rate_30d: number | null;
  mttr_minutes_30d: number | null;
  last_deploy_at: string | null;
}

export type CardStatus =
  | 'nunca' | 'ok' | 'failed' | 'failed_smoke' | 'running' | 'stale' | 'drift' | 'desconocido';

export interface TargetCard {
  key: string;
  label: string;
  kind: 'local' | 'remote';
  configured: boolean;
  protected: boolean;
  version: string | null;
  deployedAgo: string;
  status: CardStatus;
  canRollback: boolean;
}

export interface ServerRef {
  alias: string;
  host?: string;
}

export interface ConfirmRequirement {
  kind: 'checkbox' | 'text';
  expected?: string;
}

// ── buildTargetCards ─────────────────────────────────────────────────────────

/** Local SIEMPRE primero; un server registrado sin config de la app ⇒ card
 * "sin asignar" (configured=false). */
export function buildTargetCards(
  app: DeployApp | null,
  servers: ServerRef[],
  overviewState: Record<string, LedgerEntry | null | undefined>,
  now: Date = new Date(),
): TargetCard[] {
  const targets = app?.targets ?? {};
  const destKeys = ['__local__', ...servers.map((s) => s.alias)];
  return destKeys.map((key) => {
    const cfg = targets[key];
    const last = overviewState[key] ?? null;
    return {
      key,
      label: key === '__local__' ? 'Local' : key,
      kind: key === '__local__' ? 'local' : 'remote',
      configured: !!cfg,
      protected: !!cfg?.protected,
      version: last?.version_id ?? null,
      deployedAgo: last?.finished_at ? formatAgo(last.finished_at, now) : '',
      status: cardStatus(last, undefined),
      canRollback: !!cfg && !!last && (last.status === 'success' || last.status === 'failed_smoke'),
    };
  });
}

export function formatAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diffMs = now.getTime() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'hace instantes';
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return `hace ${days} d`;
}

// ── cardStatus ────────────────────────────────────────────────────────────────

export type DriftResult = 'never' | 'unknown' | 'ok' | 'drift';

/** 8 estados. `stale` = effective_status derivado de A1 (backend reiniciado a
 * mitad de deploy): badge gris "obsoleto". */
export function cardStatus(last: LedgerEntry | null | undefined, drift?: DriftResult): CardStatus {
  if (!last) return 'nunca';
  const eff = last.effective_status ?? last.status;
  if (eff === 'stale') return 'stale';
  if (eff === 'running') return 'running';
  if (eff === 'failed_smoke') return 'failed_smoke';
  if (eff === 'failed') return 'failed';
  if (eff === 'success') {
    if (drift === 'drift') return 'drift';
    if (drift === 'unknown') return 'desconocido';
    return 'ok';
  }
  return 'desconocido';
}

// ── rollbackChoices ───────────────────────────────────────────────────────────

/** Solo versiones `success` retenidas, EXCLUYENDO la activa (la más reciente
 * exitosa) y las fallidas. `history` debe venir más-reciente-primero (orden
 * del ledger, GET /history). */
export function rollbackChoices(
  history: LedgerEntry[],
  retain: number,
): { version: string; when: string }[] {
  const successes = history.filter((h) => h.status === 'success' && h.version_id);
  const seen = new Set<string>();
  const uniq: LedgerEntry[] = [];
  for (const h of successes) {
    if (!seen.has(h.version_id)) {
      seen.add(h.version_id);
      uniq.push(h);
    }
  }
  return uniq.slice(1, 1 + Math.max(0, retain)).map((h) => ({
    version: h.version_id,
    when: h.finished_at ?? h.started_at,
  }));
}

// ── confirmRequirement ────────────────────────────────────────────────────────

export function confirmRequirement(
  targetCfg: { protected?: boolean } | null | undefined,
  appId: string,
): ConfirmRequirement {
  if (targetCfg?.protected) {
    return { kind: 'text', expected: appId };
  }
  return { kind: 'checkbox' };
}

// ── waveOrder ─────────────────────────────────────────────────────────────────

/** El operador elige el orden de destinos (canary humano = ola de 1 +
 * promover al resto); se respeta el orden de SELECCIÓN, sin duplicados. */
export function waveOrder(selectedKeys: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const k of selectedKeys) {
    if (!seen.has(k)) {
      seen.add(k);
      out.push(k);
    }
  }
  return out;
}

// ── formatDora ────────────────────────────────────────────────────────────────

export function formatDora(metrics: DoraMetrics): { label: string; value: string }[] {
  const pct = metrics.change_failure_rate_30d == null
    ? '—' : `${Math.round(metrics.change_failure_rate_30d * 100)}%`;
  const mttr = metrics.mttr_minutes_30d == null
    ? '—' : `${Math.round(metrics.mttr_minutes_30d)} min`;
  return [
    { label: 'Deploys (7d)', value: String(metrics.deploys_7d) },
    { label: 'Deploys (30d)', value: String(metrics.deploys_30d) },
    { label: 'Change failure rate (30d)', value: pct },
    { label: 'MTTR (30d)', value: mttr },
  ];
}

// ── buildPendingPresetHandoff (F8) ───────────────────────────────────────────

export function buildPendingPresetHandoff(stack: string | null): { presetId: string } | null {
  return stack ? { presetId: stack } : null;
}

// ── consumePendingPreset (F8) ────────────────────────────────────────────────

export function consumePendingPreset(storageValue: string | null): { presetId: string } | null {
  if (!storageValue) return null;
  try {
    const parsed = JSON.parse(storageValue);
    if (parsed && typeof parsed.presetId === 'string' && parsed.presetId) {
      return { presetId: parsed.presetId };
    }
    return null;
  } catch {
    return null;
  }
}

// ── showCreatePipelineCta (F8) ───────────────────────────────────────────────

export function showCreatePipelineCta(
  health: Record<string, boolean | undefined> | null | undefined,
): boolean {
  return health?.stack_detect_enabled === true;
}

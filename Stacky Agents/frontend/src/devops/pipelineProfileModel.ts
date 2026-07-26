/** Plan 247 F5 — modelo puro del perfil de pipeline. Sin DOM, sin React, sin fetch.
 *  Espejo del contrato congelado de services/pipeline_profiler.py (CONTRACT_VERSION 247.1). */

export type Confidence = 'alta' | 'media' | 'desconocido';

export interface EvidenceDto {
  location: string;
  detail: string;
}

export interface ProfileFieldDto<T> {
  value: T;
  confidence: Confidence;
  evidence: EvidenceDto[];
}

export interface EnvironmentRefDto {
  name: string;
  kind: string;
  resolved: boolean;
  possible_values: string[];
}

export interface AgentPoolDto {
  kind: string;
  name: string;
  os: boolean | null;
}

export interface PipelineProfileDto {
  contract_version: string;
  source_path: string;
  stack: ProfileFieldDto<string[]>;
  phases: Record<string, ProfileFieldDto<boolean>>;
  artifacts_published: ProfileFieldDto<string[]>;
  artifacts_consumed: ProfileFieldDto<string[]>;
  environments: ProfileFieldDto<EnvironmentRefDto[]>;
  agents: ProfileFieldDto<AgentPoolDto[]>;
  triggers: ProfileFieldDto<string[]>;
  purpose: string;
  purpose_source: 'plantilla' | 'llm';
  not_understood: string[];
  parse_error: string | null;
}

export interface ProfileRow {
  label: string;
  text: string;
  confidence: Confidence;
  evidence: string[];
  tone: 'ok' | 'gap' | 'unknown';
}

export const PHASE_LABELS: Record<string, string> = {
  build: 'Compila',
  test: 'Testea',
  package: 'Empaqueta',
  publish_artifact: 'Publica artefactos',
  deploy: 'Despliega',
};

export const STACK_LABELS: Record<string, string> = {
  dotnet_framework: '.NET Framework',
  dotnet_core: '.NET Core',
  sql_dacpac: 'SQL/DACPAC',
  node: 'Node',
  python: 'Python',
  container: 'contenedores',
};

const TRIGGER_LABELS: Record<string, string> = {
  push: 'push',
  pr: 'pull request',
  scheduled: 'agendado',
  manual: 'manual',
};

export function confidenceLabel(c: Confidence): string {
  if (c === 'alta') return 'confianza alta';
  if (c === 'media') return 'confianza media';
  return 'no determinado';
}

function evidenceTexts(field: { evidence?: EvidenceDto[] } | undefined): string[] {
  return (field?.evidence ?? []).map((e) => `${e.location}: ${e.detail}`);
}

function isBroken(p: PipelineProfileDto | null): boolean {
  return !p || !!p.parse_error;
}

/** Una fila por fase de PHASE_LABELS. La ausencia VERIFICADA se ve distinta de la dudosa. */
export function phaseRows(p: PipelineProfileDto | null): ProfileRow[] {
  if (isBroken(p)) return [];
  const profile = p as PipelineProfileDto;
  return Object.keys(PHASE_LABELS).map((id) => {
    const field = profile.phases?.[id];
    const value = field?.value === true;
    const confidence: Confidence = field?.confidence ?? 'desconocido';
    let tone: ProfileRow['tone'];
    if (value) tone = 'ok';
    else if (confidence === 'desconocido') tone = 'unknown';
    else tone = 'gap';
    let text: string;
    if (value) text = 'si';
    else if (confidence === 'desconocido') text = 'no se pudo determinar';
    else text = 'no';
    return {
      label: PHASE_LABELS[id],
      text,
      confidence,
      evidence: evidenceTexts(field),
      tone,
    };
  });
}

function formatEnvironments(refs: EnvironmentRefDto[]): string {
  return refs
    .map((e) => (e.resolved ? e.name : `${e.name} (sin resolver)`))
    .join(', ');
}

function formatAgents(pools: AgentPoolDto[]): string {
  return pools
    .map((a) => {
      if (a.kind === 'hosted') return `hosted ${a.name}`;
      if (a.kind === 'self_hosted') return `self-hosted ${a.name}`;
      return 'agente heredado';
    })
    .join(' + ');
}

/** Filas de resumen. NUNCA imprime [object Object]. */
export function summaryRows(p: PipelineProfileDto | null): ProfileRow[] {
  if (isBroken(p)) return [];
  const profile = p as PipelineProfileDto;
  const rows: ProfileRow[] = [];

  const stackIds = profile.stack?.value ?? [];
  rows.push({
    label: 'Tecnologia',
    text: stackIds.length
      ? stackIds.map((s) => STACK_LABELS[s] ?? s).join(', ')
      : 'no determinada',
    confidence: profile.stack?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.stack),
    tone: stackIds.length ? 'ok' : 'unknown',
  });

  const agents = profile.agents?.value ?? [];
  rows.push({
    label: 'Agente',
    text: agents.length ? formatAgents(agents) : 'no declarado',
    confidence: profile.agents?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.agents),
    tone: agents.length ? 'ok' : 'unknown',
  });

  const triggers = profile.triggers?.value ?? [];
  rows.push({
    label: 'Dispara',
    text: triggers.length ? triggers.map((t) => TRIGGER_LABELS[t] ?? t).join(', ') : 'sin datos',
    confidence: profile.triggers?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.triggers),
    tone: triggers.length ? 'ok' : 'unknown',
  });

  const publicados = profile.artifacts_published?.value ?? [];
  rows.push({
    label: 'Publica',
    text: publicados.length ? publicados.join(', ') : 'nada',
    confidence: profile.artifacts_published?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.artifacts_published),
    tone: publicados.length ? 'ok' : 'gap',
  });

  const consumidos = profile.artifacts_consumed?.value ?? [];
  rows.push({
    label: 'Consume',
    text: consumidos.length ? consumidos.join(', ') : 'nada',
    confidence: profile.artifacts_consumed?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.artifacts_consumed),
    tone: consumidos.length ? 'ok' : 'gap',
  });

  const entornos = profile.environments?.value ?? [];
  rows.push({
    label: 'Ambientes',
    text: entornos.length ? formatEnvironments(entornos) : 'ninguno',
    confidence: profile.environments?.confidence ?? 'desconocido',
    evidence: evidenceTexts(profile.environments),
    tone: entornos.length ? 'ok' : 'gap',
  });

  return rows;
}

/** 'No corre tests' SOLO con ausencia VERIFICADA (value false + confianza alta). */
export function gapHeadline(p: PipelineProfileDto | null): string | null {
  if (isBroken(p)) return null;
  const test = (p as PipelineProfileDto).phases?.test;
  if (test && test.value === false && test.confidence === 'alta') return 'No corre tests';
  return null;
}

/** C21 — el 501 del plan 246 se traduce a una instruccion accionable, no a un codigo crudo. */
export function profileErrorCopy(message: string): string {
  if ((message || '').includes('inventory_unavailable')) {
    return 'Inventario de pipelines no disponible (plan 246): pegá el YAML';
  }
  return message;
}

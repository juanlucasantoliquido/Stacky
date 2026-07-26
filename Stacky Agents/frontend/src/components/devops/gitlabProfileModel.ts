/** Plan 249 F5 — modelo puro de los hallazgos semánticos GitLab (GL000..GL011).
 *
 *  REUSA `groupFindings` de `pipelineLint.ts` en vez de reimplementar la agrupación, y
 *  vive en la MISMA carpeta que el panel que lo consume. Lo único genuinamente nuevo
 *  acá es la tabla de títulos.
 */
import { groupFindings, type GroupedFindings, type LintFinding } from './pipelineLint';

/** Un SemanticFinding del backend (cicd_semantic_rules.SemanticFinding, 5 campos). */
export type GitlabSemanticFinding = {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  location: string;
  evidence: string;
};

/** GL000..GL011 -> título corto en español. */
export const GL_RULE_TITLES: Readonly<Record<string, string>> = {
  GL000: 'Documento fuera de rango o ilegible',
  GL001: 'Job en un stage no declarado',
  GL002: 'needs a un job de un stage posterior',
  GL003: 'only/except mezclado con rules',
  GL004: 'only/except legado',
  GL005: 'Deploy a produccion sin compuerta humana',
  GL006: 'extends a un template ausente',
  GL007: 'tags que exigen un runner que no existe',
  GL008: 'artifacts:paths que el job no produce',
  GL009: 'Job sin imagen ni runner resolubles',
  GL010: 'Keyword fuera del catalogo',
  GL011: 'Pipeline generado sin un solo comando real',
};

/** Adapta un SemanticFinding a la forma `LintFinding` que el panel YA sabe renderizar. */
export function toLintFinding(f: GitlabSemanticFinding): LintFinding {
  return {
    code: f.code,
    severity: f.severity,
    message: f.message,
    line: null,
    node: f.location,
    fix: null,
  };
}

/** Agrupa REUSANDO groupFindings de pipelineLint.ts. No reimplementa nada. */
export function groupSemantic(fs: GitlabSemanticFinding[]): GroupedFindings {
  return groupFindings((fs || []).map(toLintFinding));
}

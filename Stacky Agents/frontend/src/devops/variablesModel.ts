/**
 * variablesModel.ts — Plan 94 F4.
 * Espejo PURO (sin I/O) de services/ci_variables.py (backend). Paridad de datos
 * verificada por test contra el MISMO fixture compartido
 * backend/tests/fixtures/plan94_secret_hints.json (patrón 88).
 */
import type { PipelineSpecDraft } from './specBuilder';

const KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
// Espejo EXACTO de _SECRET_HINT_RE en services/ci_variables.py (incluida la
// regla CRED(?!IT) — C7: no matchear CREDIT_LIMIT).
const SECRET_HINT_RE = /(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED(?!IT)|CONN(ECTION)?_?STR)/i;

/** Espejo de validate_variable_key (ci_variables.py). None (null) si OK. */
export function validateVariableKey(key: string): string | null {
  if (!key) return 'La key no puede estar vacía';
  if (key.length > 255) return 'La key excede los 255 caracteres';
  if (!KEY_RE.test(key)) {
    return "La key debe empezar con letra o '_' y contener solo letras, dígitos y '_'";
  }
  return null;
}

/** Espejo de looks_secret (ci_variables.py). Solo por key, nunca por valor. */
export function looksSecret(key: string): boolean {
  return SECRET_HINT_RE.test(key);
}

/**
 * canBeMasked (A2) — espejo PURO de las reglas de masking de GitLab: una sola
 * línea, longitud >= 8, charset Base64 + "@ : . ~" (C16: SIN "_" ni "-", que
 * GitLab NO acepta para masking). El value nunca se persiste: se evalúa
 * on-change y se descarta. El backend (reintento C8) sigue siendo la fuente
 * de verdad.
 */
const MASKABLE_RE = /^[a-zA-Z0-9+/=@:.~]{8,}$/;
export function canBeMasked(value: string): boolean {
  if (/[\n\r]/.test(value)) return false;
  return MASKABLE_RE.test(value);
}

/**
 * splitSpecVariables — separa spec.variables en las que "parecen secreto" por
 * key (candidatas a "Mover a variable segura") y el resto. Inmutable/puro.
 */
export function splitSpecVariables(spec: Pick<PipelineSpecDraft, 'variables'>): {
  secretLooking: string[];
  plain: string[];
} {
  const secretLooking: string[] = [];
  const plain: string[] = [];
  for (const key of Object.keys(spec.variables ?? {})) {
    if (looksSecret(key)) {
      secretLooking.push(key);
    } else {
      plain.push(key);
    }
  }
  return { secretLooking, plain };
}

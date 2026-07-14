/**
 * doctorModel.ts — Plan 96 F4. PURO: sin fetch, sin React, sin efectos.
 * Tipos + helpers de texto para el Doctor de pipelines (capas 1 y 2).
 */

export interface DoctorMatch {
  id: string;
  title: string;
  hint: string;
  line_no: number;
}

export interface DoctorDiagnosis {
  matches: DoctorMatch[];
  snippet: string;
}

export interface DoctorJob {
  job_id: string;
  name: string;
  stage: string;
  web_url?: string | null;
  diagnosis: DoctorDiagnosis;
}

/**
 * Construye el prompt para "Explicar con el agente DevOps" (capa 2).
 * Plantilla FIJA y determinista: siempre incluye el proyecto, un resumen por
 * job (título del primer match, o el fallback honesto si no matcheó nada) y
 * el snippet del primer job. Recuerda SIEMPRE la regla CONFIRMO (R-HITL del
 * plan 90) — anti-drift verificado por test.
 */
export function buildAgentPrompt(project: string, jobs: DoctorJob[]): string {
  const jobLines = jobs
    .map((job) => {
      const firstMatch = job.diagnosis.matches[0];
      const desc = firstMatch ? firstMatch.title : 'sin patron reconocido';
      return `- Job "${job.name}": ${desc}`;
    })
    .join('\n');

  const firstSnippet = jobs.length > 0 ? jobs[0].diagnosis.snippet : '';

  return (
    `Fallo el pipeline del proyecto ${project}. Diagnostico automatico:\n` +
    `${jobLines}\n` +
    `Fragmento del log:\n` +
    `${firstSnippet}\n` +
    `Explicame en llano la causa mas probable y proponeme el fix concreto.\n` +
    `Recorda: cualquier accion mutante requiere mi CONFIRMO.`
  );
}

/**
 * Línea de resumen para el encabezado del panel ("2 jobs fallaron: comando
 * inexistente, archivo no encontrado"). Si un job no matcheó nada, usa el
 * fallback honesto en vez de inventar un título.
 */
/**
 * Plan 127 — true si el health del panel habilita el doctor local (conjunción
 * flag AND LOCAL_LLM_ENABLED calculada server-side, H5). null/undefined ⇒ false.
 */
export function canUseLocalDoctor(health: { local_doctor_enabled?: boolean } | null): boolean {
  return health?.local_doctor_enabled === true;
}

/** Plan 127 — body del POST .../doctor/local (mismo contrato que el cloud menos runtime). */
export function buildLocalDoctorBody(
  project: string,
  payload: object,
): { project: string; payload: object } {
  return { project, payload };
}

export function summaryLine(jobs: DoctorJob[]): string {
  if (jobs.length === 0) {
    return 'No se encontraron jobs fallidos.';
  }
  const titles = jobs.map((job) => {
    const firstMatch = job.diagnosis.matches[0];
    return firstMatch ? firstMatch.title : 'sin patron reconocido';
  });
  const noun = jobs.length === 1 ? 'job fallo' : 'jobs fallaron';
  return `${jobs.length} ${noun}: ${titles.join(', ')}`;
}

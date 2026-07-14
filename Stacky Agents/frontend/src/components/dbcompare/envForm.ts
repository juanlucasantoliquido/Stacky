// Plan 122 F5 — lógica pura de validación del form de ambientes del Comparador de BD.
// Sin dependencias de React: testeable con vitest puro (gap RTL/jsdom preexistente,
// ver ConnectionHealthStrip.test.tsx:1-8).

const ALIAS_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;
const ENGINES = ["sqlserver", "oracle"] as const;

export interface EnvironmentFormValues {
  alias: string;
  engine: string;
  host: string;
  port: number | string;
  database: string;
  username: string;
}

export interface EnvironmentFormValidation {
  ok: boolean;
  errors: Record<string, string>;
}

export function validateEnvironmentForm(values: EnvironmentFormValues): EnvironmentFormValidation {
  const errors: Record<string, string> = {};

  if (!ALIAS_RE.test(values.alias || "")) {
    errors.alias = "Alias inválido: solo letras, dígitos y _.- (1-64 caracteres, empieza alfanumérico).";
  }

  const isTestAlias = (values.alias || "").startsWith("test-");
  const engineOk = (ENGINES as readonly string[]).includes(values.engine) || (isTestAlias && values.engine === "sqlite");
  if (!engineOk) {
    errors.engine = "Motor inválido: elegí SQL Server u Oracle.";
  }

  const portNum = typeof values.port === "string" ? Number(values.port) : values.port;
  if (!Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
    errors.port = "Puerto inválido: debe ser un entero entre 1 y 65535.";
  }

  if (!values.host || !values.host.trim()) {
    errors.host = "Host requerido.";
  }
  if (!values.database || !values.database.trim()) {
    errors.database = "Database requerida.";
  }
  if (!values.username || !values.username.trim()) {
    errors.username = "Username requerido.";
  }

  return { ok: Object.keys(errors).length === 0, errors };
}

export function defaultPortFor(engine: string): number {
  return engine === "oracle" ? 1521 : 1433;
}

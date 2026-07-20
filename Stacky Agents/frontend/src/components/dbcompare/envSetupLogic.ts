// Plan 157 F4 — lógica pura del wizard de alta de ambientes (testeable con vitest;
// gap RTL/jsdom preexistente, ver envForm.ts:1-3). Sin dependencias de React ni del
// cliente HTTP.
import type { EnvironmentFormValues } from "./envForm";
import { defaultPortFor } from "./envForm";

/** Preview seguro que devuelve el backend (sin password, sin masked_raw). */
export interface ImportPreview {
  name: string;
  engine: string; // "sqlserver" | "oracle" | "" (no inferible)
  host: string;
  port: number | null;
  database: string;
  username: string;
  integrated_security: boolean;
  has_password: boolean;
  index: number;
}

export type SetupMode = "datasource" | "webconfig" | "manual";

export interface SetupFlags {
  webconfigImportEnabled: boolean;
}

/** Arma los EnvironmentFormValues desde un preview. engine "" → default sqlserver;
 * port null → puerto default del engine resultante. */
export function mapPreviewToForm(preview: ImportPreview): EnvironmentFormValues {
  const engine = preview.engine === "" ? "sqlserver" : preview.engine;
  const port =
    preview.port === null || preview.port === undefined ? defaultPortFor(engine) : preview.port;
  return {
    alias: preview.name || "",
    engine,
    host: preview.host || "",
    port,
    database: preview.database || "",
    username: preview.username || "",
  };
}

/** Modo inicial: siempre "datasource" (A es el default del wizard). */
export function chooseInitialMode(_flags: SetupFlags): SetupMode {
  return "datasource";
}

/** Modos disponibles: "webconfig" (B) sólo si la flag de import está ON. */
export function availableModes(flags: SetupFlags): SetupMode[] {
  return flags.webconfigImportEnabled
    ? ["datasource", "webconfig", "manual"]
    : ["datasource", "manual"];
}

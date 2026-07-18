// Plan 157 F2/F4 — cliente HTTP del import local de web.config/datasource.
// Vive en un módulo propio (no en api/endpoints.ts) e importa el cliente `api`
// directamente de ./client — el patrón de DbCompare.* de endpoints.ts.
import { api } from "../../api/client";
import type { ImportPreview } from "./envSetupLogic";

export interface ImportConfigResponse {
  ok: boolean;
  import_id?: string;
  connections?: ImportPreview[];
  error?: string;
}

export interface ConfirmImportResponse {
  ok: boolean;
  alias?: string;
  password_warning?: string;
  error?: string;
}

export interface ConfirmOverrides {
  engine?: string;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
}

export const DbCompareImport = {
  /** Parsea un web.config/datasource local y devuelve previews enmascarados. */
  importConfig: (payload: { content?: string; path?: string }) =>
    api.post<ImportConfigResponse>("/api/db-compare/environments/import-config", payload),

  /** Confirma UNA conexión del import y crea el ambiente (password → keyring). */
  confirmImport: (payload: {
    import_id: string;
    index: number;
    alias: string;
    overrides?: ConfirmOverrides;
  }) =>
    api.post<ConfirmImportResponse>(
      "/api/db-compare/environments/import-config/confirm",
      payload,
    ),
};

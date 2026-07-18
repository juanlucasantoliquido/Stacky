// Plan 157 F4 — tests puros del wizard de alta (vitest, sin jsdom).
import { describe, it, expect } from "vitest";
import {
  availableModes,
  chooseInitialMode,
  mapPreviewToForm,
  type ImportPreview,
} from "../envSetupLogic";

const base: ImportPreview = {
  name: "Dev",
  engine: "sqlserver",
  host: "h",
  port: 1433,
  database: "RS",
  username: "u",
  integrated_security: false,
  has_password: true,
  index: 0,
};

describe("mapPreviewToForm", () => {
  it("usa el engine detectado", () => {
    expect(mapPreviewToForm({ ...base, engine: "oracle", port: 1521 }).engine).toBe("oracle");
  });
  it("engine vacío → sqlserver por default", () => {
    expect(mapPreviewToForm({ ...base, engine: "" }).engine).toBe("sqlserver");
  });
  it("port null → puerto default del engine resultante", () => {
    expect(mapPreviewToForm({ ...base, engine: "oracle", port: null }).port).toBe(1521);
    expect(mapPreviewToForm({ ...base, engine: "", port: null }).port).toBe(1433);
  });
  it("copia alias(name)/host/database/username", () => {
    const f = mapPreviewToForm(base);
    expect(f.alias).toBe("Dev");
    expect(f.host).toBe("h");
    expect(f.database).toBe("RS");
    expect(f.username).toBe("u");
  });
});

describe("chooseInitialMode / availableModes", () => {
  it("modo inicial siempre datasource", () => {
    expect(chooseInitialMode({ webconfigImportEnabled: true })).toBe("datasource");
    expect(chooseInitialMode({ webconfigImportEnabled: false })).toBe("datasource");
  });
  it("webconfig oculto si la flag de import está OFF", () => {
    expect(availableModes({ webconfigImportEnabled: false })).not.toContain("webconfig");
    expect(availableModes({ webconfigImportEnabled: false })).toEqual(["datasource", "manual"]);
  });
  it("webconfig visible si la flag de import está ON", () => {
    expect(availableModes({ webconfigImportEnabled: true })).toContain("webconfig");
  });
});

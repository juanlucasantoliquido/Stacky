import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Plan 273 F1 (B-03) — el shell v2 arranca alineado con el default del backend y
 * un fallo de /api/diag/health NO degrada la arquitectura de navegacion.
 *
 * Test PURO de archivos (fs + regex): RTL y jsdom NO estan instalados en este
 * repo (frontend/package.json declara solo @types/react, @types/react-dom,
 * @vitejs/plugin-react, typescript, vite, vitest), asi que esta prohibido
 * especificar un test de componente. Ver plan 273 SS3.2.
 */

const SRC = resolve(__dirname, "..");
const APP_TSX = readFileSync(resolve(SRC, "App.tsx"), "utf8");
const SHELL_NAV = readFileSync(resolve(SRC, "components/shell/shellNav.ts"), "utf8");
const CONFIG_PY = readFileSync(
  resolve(SRC, "../../backend/config.py"),
  "utf8"
);

describe("plan273 F1 — default del shell v2 (B-03)", () => {
  it("paridad_default_backend_frontend", () => {
    // El default EFECTIVO del backend vive en el os.getenv de config.py.
    const m = CONFIG_PY.match(
      /STACKY_UI_SHELL_V2_ENABLED"\s*,\s*"(true|false)"/
    );
    expect(m, "no se encontro el os.getenv de STACKY_UI_SHELL_V2_ENABLED en backend/config.py").toBeTruthy();
    const backendDefault = m![1] === "true";

    const f = SHELL_NAV.match(/export const SHELL_V2_DEFAULT\s*=\s*(true|false)\s*;/);
    expect(f, "shellNav.ts no exporta SHELL_V2_DEFAULT").toBeTruthy();
    const frontendDefault = f![1] === "true";

    expect(
      frontendDefault,
      `SHELL_V2_DEFAULT=${frontendDefault} pero el backend default es ${backendDefault}. ` +
        `El espejo se rompio: si cambio el default del backend, este literal cambia en el MISMO commit.`
    ).toBe(backendDefault);
  });

  it("app_no_inicializa_shellv2_en_false_literal", () => {
    const offenders = APP_TSX.split("\n")
      .map((l, i) => [i + 1, l] as const)
      .filter(([, l]) => /shellV2Enabled/.test(l) && /useState\(false\)/.test(l));
    expect(
      offenders.map(([n, l]) => `App.tsx:${n}: ${l.trim()}`),
      "shellV2Enabled sigue arrancando en false: la nav v1 se pinta en el primer paint de TODA carga"
    ).toEqual([]);
  });

  it("el_catch_del_health_no_apaga_el_shell", () => {
    const offenders = APP_TSX.split("\n")
      .map((l, i) => [i + 1, l] as const)
      .filter(([, l]) => /setShellV2Enabled\(false\)/.test(l));
    expect(
      offenders.map(([n, l]) => `App.tsx:${n}: ${l.trim()}`),
      "un fallo de red sigue degradando la nav a v1 para toda la sesion (H-02)"
    ).toEqual([]);
  });

  it("una_clave_ausente_no_degrada_la_nav", () => {
    // C8: `=== true` trata "clave ausente" como "apagado" y reintroduce el
    // cambio de nav despues del primer paint con un health 200 incompleto.
    // El precedente de la casa es `!== false` (plan 172 F2, ui_shortcuts_enabled).
    expect(
      /shell_v2_enabled === true/.test(APP_TSX),
      "App.tsx todavia usa `shell_v2_enabled === true`: un 200 sin la clave degrada la nav"
    ).toBe(false);
    expect(
      /shell_v2_enabled !== false/.test(APP_TSX),
      "App.tsx no usa `shell_v2_enabled !== false`"
    ).toBe(true);
  });
});

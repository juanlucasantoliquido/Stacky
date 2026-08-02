/**
 * plan293Patas.test.ts — Plan 293 F13. LAS 13 PATAS del tab nuevo.
 *
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/plan293Patas.test.ts
 *
 * POR QUÉ EXISTE
 * --------------
 * Un tab nuevo en este frontend son 13 lugares, y `tsc` sólo exige DOS
 * (`TAB_PATHS` y `TAB_META`, los dos `Record<Tab, …>`). Las otras once fallan
 * MUDAS: el tab no aparece en la barra, o aparece pero el enlace directo muere,
 * o queda sin icono — y ni el compilador ni ningún test lo notan.
 *
 * Este archivo es de TEXTO a propósito: no hay forma de verificar por tipos que
 * alguien se acordó de agregar la entrada al array de grupos.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { TAB_PATHS } from "../routes";
import { TAB_META, SHELL_NAV_GROUPS, computeVisibleTabs } from "../../components/shell/shellNav";
import { ICON_BY_NAME } from "../../components/shell/shellIcons";
import { NAV_COMMANDS } from "../../components/commandPaletteData";

const TAB = "publicar";
const RUTA = "/publicar";
const SRC = resolve(__dirname, "../..");

const leer = (rel: string) => readFileSync(resolve(SRC, rel), "utf-8");
const appTsx = () => leer("App.tsx");

describe("plan 293 F13 — las 13 patas del tab", () => {
  it("pata 1 — el tab está en la unión `Tab` de routes.ts", () => {
    expect(leer("services/routes.ts")).toContain(`| "${TAB}"`);
  });

  it("pata 2 — TAB_PATHS tiene su ruta (tsc lo exige)", () => {
    expect(TAB_PATHS[TAB as keyof typeof TAB_PATHS]).toBe(RUTA);
  });

  it("pata 3 — la unión `ShellTab` está sincronizada a mano con `Tab`", () => {
    expect(leer("components/shell/shellNav.ts")).toContain(`| "${TAB}"`);
  });

  it("pata 4 — TAB_META tiene rótulo e icono (tsc lo exige)", () => {
    const meta = TAB_META[TAB as keyof typeof TAB_META];
    expect(meta).toBeDefined();
    expect(meta.label).toBe("Publicar mi trabajo");
    expect(meta.iconName.length).toBeGreaterThan(0);
  });

  it("pata 5 — el icono está importado Y en ICON_BY_NAME (son DOS ediciones)", () => {
    const meta = TAB_META[TAB as keyof typeof TAB_META];
    expect(ICON_BY_NAME[meta.iconName], `falta ${meta.iconName} en ICON_BY_NAME`).toBeDefined();
    expect(leer("components/shell/shellIcons.ts")).toContain(meta.iconName);
  });

  it("pata 6 — el tab está en un grupo de la barra (sin esto NO aparece y no hay error)", () => {
    const enGrupos = SHELL_NAV_GROUPS.flatMap((g) => g.tabs);
    expect(enGrupos).toContain(TAB);
    // Y en UNO SOLO.
    expect(enGrupos.filter((t) => t === TAB)).toHaveLength(1);
  });

  it("pata 7 — VisibilityInput declara su campo", () => {
    expect(leer("components/shell/shellNav.ts")).toContain("publicarEnabled");
  });

  it("pata 8 — computeVisibleTabs lo agrega sólo con su gate encendido", () => {
    const base = {
      sections: { team: false, pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
      costCenterEnabled: false, planesEnabled: false, evolutionEnabled: false,
    };
    expect(computeVisibleTabs({ ...base }).has(TAB as never)).toBe(false);
    expect(computeVisibleTabs({ ...base, publicarEnabled: true }).has(TAB as never)).toBe(true);
  });

  it("pata 9 — App.tsx declara el estado del gate", () => {
    expect(appTsx()).toMatch(/publicarGate.*useState<GateState>\("unknown"\)/);
  });

  it("pata 10 — App.tsx sondea el health del backend", () => {
    expect(appTsx()).toContain('probeFlagHealth("/api/workbench/health")');
  });

  it("pata 11 — App.tsx redirige si el gate resolvió apagado", () => {
    expect(appTsx()).toMatch(/tab === "publicar" && shouldRedirectAway\(publicarGate\)/);
  });

  it("pata 12 — App.tsx alimenta la visibilidad con isGateOn, NUNCA el string suelto", () => {
    const src = appTsx();
    expect(src).toContain("publicarEnabled: isGateOn(publicarGate)");
    // `"off"` es TRUTHY: `{publicarGate && <X/>}` mostraría el tab apagado con
    // tsc en verde y cero tests rojos.
    expect(src).not.toMatch(/\{\s*publicarGate\s*&&/);
  });

  it("pata 13 — App.tsx monta la página, con esqueleto mientras resuelve", () => {
    const src = appTsx();
    expect(src).toContain("isGateResolving(publicarGate)");
    expect(src).toContain("isGateOn(publicarGate) && <WorkbenchPage />");
    expect(src).toContain('import WorkbenchPage from "./pages/WorkbenchPage"');
  });

  it("pata extra — la paleta de comandos puede llegar al tab", () => {
    const cmd = NAV_COMMANDS.find((c) => c.path === RUTA);
    expect(cmd, "el tab existe pero Ctrl+K no llega").toBeDefined();
    expect(cmd!.label).toContain("Publicar");
  });

  it("D6 — el id del tab NO colisiona con el id de un grupo de la barra", () => {
    const idsDeGrupo = SHELL_NAV_GROUPS.map((g) => g.id);
    expect(idsDeGrupo).toContain("trabajo");
    expect(idsDeGrupo).not.toContain(TAB);
    expect(TAB).not.toBe("trabajo");
  });
});

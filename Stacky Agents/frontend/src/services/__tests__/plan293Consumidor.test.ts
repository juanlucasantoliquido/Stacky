/**
 * plan293Consumidor.test.ts — Plan 293 F5, el gate del CONSUMIDOR.
 *
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/plan293Consumidor.test.ts
 *
 * POR QUÉ EXISTE
 * --------------
 * `CodexConsoleFull.tsx` arma su lista enumerando las claves de
 * `GroupedRepoFiles` A MANO. Agregar una clave a la interfaz y no agregarla ahí
 * hace DESAPARECER esos archivos de la pantalla de Repositorio que hoy funciona
 * — y ni `tsc` ni ningún otro test lo notan, porque el objeto sigue siendo
 * válido y el array sigue compilando.
 *
 * Es una regresión visible para el usuario y silenciosa para el compilador, así
 * que el único gate posible es de TEXTO.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const CONSUMIDOR = resolve(__dirname, "../../components/CodexConsoleFull.tsx");
const MODELO = resolve(__dirname, "../consoleRepoPanel.ts");

function leer(p: string): string {
  return readFileSync(p, "utf-8");
}

/** Las claves declaradas en la interfaz, extraídas del propio archivo: si
 *  mañana se agrega una octava, este test la exige sin que nadie lo edite. */
function clavesDeclaradas(): string[] {
  const src = leer(MODELO);
  const bloque = src.split("export interface GroupedRepoFiles {")[1]?.split("}")[0] ?? "";
  return [...bloque.matchAll(/^\s*(\w+)\s*:/gm)].map((m) => m[1]);
}

describe("plan 293 F5 — el consumidor de producción muestra TODOS los grupos", () => {
  it("la interfaz declara las siete claves esperadas", () => {
    expect(clavesDeclaradas().sort()).toEqual(
      ["conflictos", "deleted", "modified", "new", "otros", "renombrados", "untracked"].sort(),
    );
  });

  it("CodexConsoleFull enumera TODAS las claves de GroupedRepoFiles", () => {
    const src = leer(CONSUMIDOR);
    const arranque = src.indexOf("const groups:");
    expect(arranque).toBeGreaterThan(-1);
    const bloque = src.slice(arranque, src.indexOf("];", arranque));

    const faltantes = clavesDeclaradas().filter((k) => !bloque.includes(`grouped.${k}`));
    expect(faltantes).toEqual([]);
  });

  it("los conflictos se muestran PRIMEROS: son lo urgente", () => {
    const src = leer(CONSUMIDOR);
    const arranque = src.indexOf("const groups:");
    const bloque = src.slice(arranque, src.indexOf("];", arranque));
    const posConflictos = bloque.indexOf("grouped.conflictos");
    const posModificados = bloque.indexOf("grouped.modified");
    expect(posConflictos).toBeGreaterThan(-1);
    expect(posConflictos).toBeLessThan(posModificados);
  });

  it("el rótulo de los conflictos está en castellano y sin jerga", () => {
    const src = leer(CONSUMIDOR);
    expect(src).toContain('"En conflicto"');
    const arranque = src.indexOf("const groups:");
    const bloque = src.slice(arranque, src.indexOf("];", arranque));
    for (const jerga of ["merge", "unmerged", "conflict ", "staged"]) {
      expect(bloque.toLowerCase()).not.toContain(jerga);
    }
  });
});

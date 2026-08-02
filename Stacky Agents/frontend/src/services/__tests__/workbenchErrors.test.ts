/**
 * workbenchErrors.test.ts — Plan 293 F12.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/workbenchErrors.test.ts
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { traducir, codigosCubiertos, JERGA_PROHIBIDA } from "../workbenchErrors";

/** Los códigos que el backend puede devolver, extraídos del PROPIO backend.
 *  Así, si mañana se agrega un código y no su traducción, este test lo caza. */
function codigosDelBackend(): string[] {
  const base = resolve(__dirname, "../../../../backend/services");
  const textos = [
    readFileSync(resolve(base, "git_workbench.py"), "utf-8"),
    readFileSync(resolve(base, "git_local_writer.py"), "utf-8"),
  ].join("\n");

  const codigos = new Set<string>();
  // Los frozenset de códigos del semáforo.
  for (const bloque of ["CODIGOS_BLOQUEO", "CODIGOS_AVISO"]) {
    const trozo = textos.split(`${bloque} = frozenset({`)[1]?.split("})")[0] ?? "";
    for (const m of trozo.matchAll(/"([a-z_]+)"/g)) codigos.add(m[1]);
  }
  // Los códigos que devuelve el escritor: _fallo("codigo", ...)
  for (const m of textos.matchAll(/_fallo\(\s*\n?\s*"([a-z_]+)"/g)) codigos.add(m[1]);
  for (const m of textos.matchAll(/"codigo": "([a-z_]+)"/g)) codigos.add(m[1]);
  return [...codigos].sort();
}

describe("workbenchErrors — el diccionario llano", () => {
  it("1. cubre TODOS los códigos que el backend puede devolver", () => {
    const delBackend = codigosDelBackend();
    expect(delBackend.length).toBeGreaterThan(15);
    const cubiertos = new Set(codigosCubiertos());
    const faltantes = delBackend.filter((c) => !cubiertos.has(c));
    expect(faltantes).toEqual([]);
  });

  it("2. cada traducción tiene las cuatro partes, y ninguna vacía", () => {
    for (const codigo of codigosCubiertos()) {
      const t = traducir(codigo);
      expect(t.titulo.length, codigo).toBeGreaterThan(5);
      expect(t.queSignifica.length, codigo).toBeGreaterThan(15);
      expect(t.queHacer.length, codigo).toBeGreaterThan(10);
      expect(["bloqueo", "aviso"]).toContain(t.tono);
    }
  });

  it("3. NINGUNA traducción usa jerga técnica", () => {
    const conJerga: string[] = [];
    for (const codigo of codigosCubiertos()) {
      const t = traducir(codigo);
      const texto = `${t.titulo} ${t.queSignifica} ${t.queHacer}`.toLowerCase();
      for (const jerga of JERGA_PROHIBIDA) {
        // Palabra completa, para no marcar "empujar" por "push".
        if (new RegExp(`\\b${jerga}\\b`).test(texto)) conJerga.push(`${codigo}: ${jerga}`);
      }
    }
    expect(conJerga).toEqual([]);
  });

  it("4. un código desconocido NO devuelve el código crudo", () => {
    const t = traducir("frobnicate_exploded");
    expect(t.titulo).not.toContain("frobnicate");
    expect(t.queHacer.length).toBeGreaterThan(10);
  });

  it("5. null y undefined no lanzan", () => {
    expect(() => traducir(null)).not.toThrow();
    expect(() => traducir(undefined)).not.toThrow();
    expect(traducir("").titulo.length).toBeGreaterThan(5);
  });

  it("6. los avisos están marcados como aviso, no como bloqueo", () => {
    for (const codigo of ["hay_cambios_no_seleccionados", "rama_sin_upstream", "carrera_working_tree", "identidad_derivada"]) {
      expect(traducir(codigo).tono, codigo).toBe("aviso");
    }
  });

  it("7. el rechazo del servidor explica que NO se perdió nada", () => {
    const t = traducir("envio_rechazado");
    expect(`${t.queSignifica} ${t.queHacer}`.toLowerCase()).toContain("no se perdió nada".toLowerCase());
  });

  it("8. las opciones apagadas dicen QUÉ encender, con el rótulo exacto de la opción", () => {
    expect(traducir("escritura_apagada").queHacer).toContain("guarde cambios en tu carpeta");
    expect(traducir("push_apagado").queHacer).toContain("envíe tu trabajo al servidor");
  });

  it("9. ninguna traducción manda a 'contactar al administrador' sin dar un paso concreto", () => {
    for (const codigo of codigosCubiertos()) {
      const t = traducir(codigo);
      expect(t.queHacer.toLowerCase(), codigo).not.toMatch(/^contact/);
    }
  });
});

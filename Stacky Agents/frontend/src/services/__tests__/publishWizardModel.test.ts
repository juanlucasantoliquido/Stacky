/**
 * publishWizardModel.test.ts — Plan 293 F13, la lógica pura del asistente.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/publishWizardModel.test.ts
 */
import { describe, it, expect } from "vitest";
import {
  ESTADO_INICIAL, PASOS, agruparParaPintar, alternar, avisosParaElPrimerPaso,
  bloqueosParaElPrimerPaso, motivoParaNoAvanzar, pasoAnterior, pasoSiguiente,
  puedeAvanzar, resumenSeleccion, rotuloDe, textoContador,
  type EstadoTablero,
} from "../publishWizardModel";

const TABLERO: EstadoTablero = {
  available: true,
  archivos: [
    { path: "a.txt", grupo: "modificados" },
    { path: "b.txt", grupo: "modificados" },
    { path: "c.txt", grupo: "sin_seguimiento" },
  ],
  conflictos: [],
  semaforo: { puede: true, bloqueos: [], avisos: [] },
};

describe("publishWizardModel", () => {
  it("1. no se avanza del paso de elegir con cero archivos", () => {
    const e = { ...ESTADO_INICIAL, paso: "elegir" as const };
    expect(motivoParaNoAvanzar(e, TABLERO)).toBe("nada_seleccionado");
    expect(puedeAvanzar(e, TABLERO)).toBe(false);
  });

  it("2. no se avanza del paso de describir sin un texto mínimo", () => {
    const e = { ...ESTADO_INICIAL, paso: "describir" as const, seleccion: ["a.txt"], mensaje: "ok" };
    expect(motivoParaNoAvanzar(e, TABLERO)).toBe("mensaje_muy_corto");
    expect(puedeAvanzar({ ...e, mensaje: "arreglo el total" }, TABLERO)).toBe(true);
  });

  it("3. con conflictos NO se avanza desde NINGÚN paso", () => {
    const conConflicto = { ...TABLERO, conflictos: ["a.txt"] };
    for (const paso of PASOS) {
      const e = { ...ESTADO_INICIAL, paso, seleccion: ["a.txt"], mensaje: "un mensaje largo" };
      expect(motivoParaNoAvanzar(e, conConflicto), paso).toBe("conflictos_presentes");
    }
  });

  it("4. sin cambios no se arranca", () => {
    const vacio = { ...TABLERO, archivos: [] };
    expect(motivoParaNoAvanzar(ESTADO_INICIAL, vacio)).toBe("sin_cambios");
  });

  it("5. la carpeta no disponible gana sobre todo lo demás", () => {
    expect(motivoParaNoAvanzar(ESTADO_INICIAL, { ...TABLERO, available: false })).toBe("repo_no_disponible");
  });

  it("6. avanzar y retroceder respetan el orden y no se salen de rango", () => {
    expect(pasoSiguiente("revisar")).toBe("elegir");
    expect(pasoSiguiente("confirmar")).toBe("confirmar");
    expect(pasoAnterior("revisar")).toBe("revisar");
    expect(pasoAnterior("describir")).toBe("elegir");
  });

  it("7. alternar es inmutable y agrega/saca", () => {
    const s1 = alternar([], "a.txt");
    expect(s1).toEqual(["a.txt"]);
    expect(alternar(s1, "a.txt")).toEqual([]);
    expect(s1).toEqual(["a.txt"]); // no se mutó
  });

  it("8. el resumen NOMBRA los que quedan afuera (regla del riesgo #1)", () => {
    const r = resumenSeleccion(["a.txt"], TABLERO.archivos);
    expect(r.elegidos).toBe(1);
    expect(r.total).toBe(3);
    expect(r.noElegidos).toBe(2);
    expect(r.pathsNoElegidos.sort()).toEqual(["b.txt", "c.txt"]);
  });

  it("9. el contador está en castellano y sin jerga", () => {
    expect(textoContador(resumenSeleccion([], TABLERO.archivos))).toContain("Ninguno");
    expect(textoContador(resumenSeleccion(["a.txt"], TABLERO.archivos))).toBe("1 de 3 archivos elegidos.");
    expect(textoContador(resumenSeleccion(["a.txt", "b.txt", "c.txt"], TABLERO.archivos))).toContain("Los 3");
    expect(textoContador(resumenSeleccion([], []))).toContain("No hay archivos");
  });

  it("10. agrupar pone los conflictos PRIMERO y no pierde ningún archivo", () => {
    const grupos = agruparParaPintar([
      { path: "x", grupo: "modificados" },
      { path: "y", grupo: "conflictos" },
      { path: "z", grupo: "inventado" },
    ]);
    expect(grupos[0].grupo).toBe("conflictos");
    expect(grupos.flatMap((g) => g.archivos).length).toBe(3);
    // Un grupo desconocido cae en "Otros", nunca se pierde.
    expect(grupos.find((g) => g.grupo === "otros")?.archivos[0].path).toBe("z");
  });

  it("11. los rótulos son castellano sin jerga", () => {
    expect(rotuloDe("conflictos")).toBe("En conflicto");
    expect(rotuloDe("sin_seguimiento")).toBe("Sin seguimiento");
    expect(rotuloDe("loquesea")).toBe("Otros");
  });

  it("12. los bloqueos se muestran en el PRIMER paso, salvo el de no haber elegido", () => {
    const t: EstadoTablero = {
      ...TABLERO,
      semaforo: {
        puede: false,
        bloqueos: [{ codigo: "escritura_apagada" }, { codigo: "nada_seleccionado" }],
        avisos: [{ codigo: "identidad_derivada" }],
      },
    };
    // `nada_seleccionado` NO se muestra en el paso 1: todavía no elegiste nada
    // y mostrarlo como problema sería mentirle al usuario.
    expect(bloqueosParaElPrimerPaso(t)).toEqual(["escritura_apagada"]);
    expect(avisosParaElPrimerPaso(t)).toEqual(["identidad_derivada"]);
  });

  it("13. sin semáforo no lanza", () => {
    expect(bloqueosParaElPrimerPaso({ ...TABLERO, semaforo: undefined })).toEqual([]);
    expect(avisosParaElPrimerPaso({ ...TABLERO, semaforo: undefined })).toEqual([]);
  });
});

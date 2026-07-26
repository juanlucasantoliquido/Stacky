// Plan 200 F2 — Consola del agente dentro del detalle de la incidencia.
import { describe, it, expect } from "vitest";
import {
  execLabel,
  logLineText,
  orderExecs,
  type IncidentExecRef,
} from "./incidentConsole";

function ref(over: Partial<IncidentExecRef> = {}): IncidentExecRef {
  return { execution_id: 1, kind: "analysis", linked_at: null, ...over };
}

describe("execLabel", () => {
  it("traduce los kinds conocidos", () => {
    expect(execLabel(ref({ execution_id: 7, kind: "analysis" }))).toBe("#7 · Analisis");
    expect(execLabel(ref({ execution_id: 8, kind: "dev_resolver" }))).toBe("#8 · Dev-resolutor");
  });

  it("un kind nuevo se muestra tal cual en vez de desaparecer", () => {
    // Si mañana aparece otro tipo de ejecución, la lista tiene que seguir
    // mostrándolo: una etiqueta fea es mejor que una fila fantasma.
    expect(execLabel(ref({ execution_id: 9, kind: "qa_uat" }))).toBe("#9 · qa_uat");
  });
});

describe("orderExecs", () => {
  it("el análisis va primero: es lo que explica por qué existe el resto", () => {
    const out = orderExecs([
      ref({ execution_id: 2, kind: "dev_resolver" }),
      ref({ execution_id: 1, kind: "analysis" }),
    ]);

    expect(out.map((e) => e.execution_id)).toEqual([1, 2]);
  });

  it("dentro del mismo kind, por id ascendente", () => {
    const out = orderExecs([
      ref({ execution_id: 30, kind: "dev_resolver" }),
      ref({ execution_id: 10, kind: "dev_resolver" }),
      ref({ execution_id: 20, kind: "dev_resolver" }),
    ]);

    expect(out.map((e) => e.execution_id)).toEqual([10, 20, 30]);
  });

  it("los kinds desconocidos van al final, no se pierden", () => {
    const out = orderExecs([
      ref({ execution_id: 3, kind: "qa_uat" }),
      ref({ execution_id: 2, kind: "dev_resolver" }),
      ref({ execution_id: 1, kind: "analysis" }),
    ]);

    expect(out.map((e) => e.kind)).toEqual(["analysis", "dev_resolver", "qa_uat"]);
  });

  it("no muta la lista que recibe", () => {
    const original = [ref({ execution_id: 2, kind: "dev_resolver" }), ref({ execution_id: 1 })];
    const copia = [...original];

    orderExecs(original);

    expect(original).toEqual(copia);
  });

  it("vacío y nulo devuelven []", () => {
    expect(orderExecs([])).toEqual([]);
    expect(orderExecs(null as unknown as IncidentExecRef[])).toEqual([]);
  });
});

describe("logLineText", () => {
  it("arma timestamp, nivel y mensaje", () => {
    expect(
      logLineText({ timestamp: "2026-07-26T10:00:00Z", level: "info", message: "arrancó" }),
    ).toBe("2026-07-26T10:00:00Z [info] arrancó");
  });

  it("sin timestamp no deja un corchete vacío al principio", () => {
    expect(logLineText({ level: "error", message: "falló" })).toBe("[error] falló");
  });

  it("sin nivel tampoco inventa uno", () => {
    expect(logLineText({ timestamp: "T", message: "hola" })).toBe("T hola");
  });

  it("solo mensaje", () => {
    expect(logLineText({ message: "pelado" })).toBe("pelado");
  });

  it("un evento sin nada devuelve cadena vacía, no 'undefined'", () => {
    // Pintar "undefined undefined" en la consola haría dudar del transcript entero.
    expect(logLineText({})).toBe("");
  });
});

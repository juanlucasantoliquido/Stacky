// Plan 283 F9 — Modelo de la pantalla de Reuniones (logica pura).
//
// 9 casos. Todo en `.ts` puro: RTL/jsdom NO estan instalados y un `.test.tsx`
// con RTL reporta "no tests" con exit 0, que es un falso verde perfecto.
import { describe, it, expect } from "vitest";
import { formatDate } from "./format";
import {
  GRUPO_SIN_FECHA,
  accionesDisponibles,
  agruparPorDia,
  etiquetaEstadoMinuta,
  puedePublicar,
  resumenCalendario,
  type MeetingRow,
} from "./meetingsModel";

function fila(over: Partial<MeetingRow> = {}): MeetingRow {
  return {
    id: 1,
    subject: "Semanal",
    startedAt: "2026-08-03T14:00:00Z",
    minutesState: "done",
    pendientes: 2,
    ...over,
  };
}

describe("meetingsModel — agrupado", () => {
  it("1 — agrupa por dia local y ordena de mas reciente a mas viejo", () => {
    const grupos = agruparPorDia([
      fila({ id: 1, startedAt: "2026-08-01T09:00:00Z", subject: "Retro" }),
      fila({ id: 2, startedAt: "2026-08-03T14:00:00Z", subject: "Semanal" }),
      fila({ id: 3, startedAt: "2026-08-03T17:00:00Z", subject: "Cierre" }),
    ]);

    expect(grupos).toHaveLength(2);
    // La etiqueta se calcula con el MISMO formateador canonico, asi el caso no
    // depende de la zona horaria de la maquina que lo corre.
    expect(grupos[0].dia).toBe(formatDate("2026-08-03T14:00:00Z", "local"));
    expect(grupos[1].dia).toBe(formatDate("2026-08-01T09:00:00Z", "local"));
    // Dentro del dia tambien va de mas reciente a mas viejo.
    expect(grupos[0].rows.map((r) => r.subject)).toEqual(["Cierre", "Semanal"]);
  });

  it("2 — las reuniones sin fecha caen en un grupo propio y quedan ULTIMAS", () => {
    const grupos = agruparPorDia([
      fila({ id: 1, startedAt: null, subject: "Pegada a mano" }),
      fila({ id: 2, startedAt: "2026-08-03T14:00:00Z", subject: "Semanal" }),
    ]);

    expect(grupos).toHaveLength(2);
    expect(grupos[grupos.length - 1].dia).toBe(GRUPO_SIN_FECHA);
    expect(grupos[grupos.length - 1].rows.map((r) => r.subject)).toEqual(["Pegada a mano"]);
    // Y NO se pierde ninguna: 2 entran, 2 salen.
    expect(grupos.flatMap((g) => g.rows)).toHaveLength(2);
    expect(agruparPorDia([])).toEqual([]);
  });
});

describe("meetingsModel — estado de la minuta en castellano", () => {
  it("3 — pendiente", () => {
    expect(etiquetaEstadoMinuta("pending")).toBe("Sin texto todavia");
  });

  it("4 — lista", () => {
    expect(etiquetaEstadoMinuta("done")).toBe("Minuta lista");
  });

  it("5 — fallida", () => {
    expect(etiquetaEstadoMinuta("failed")).toBe("No se pudo generar");
  });

  it("6 — frenada por el filtro de salida de datos", () => {
    expect(etiquetaEstadoMinuta("blocked")).toBe("Frenada por datos sensibles");
    // Los 4 rotulos son distintos entre si: sin esto, una funcion que devolviera
    // siempre la misma cadena pasaria los cuatro casos.
    const todos = ["pending", "done", "failed", "blocked"].map((s) =>
      etiquetaEstadoMinuta(s as MeetingRow["minutesState"]),
    );
    expect(new Set(todos).size).toBe(4);
  });
});

describe("meetingsModel — publicacion y calendario", () => {
  it("7 — no se puede publicar con la capacidad apagada ni un compromiso ya publicado", () => {
    // GUARD POSITIVO, PRIMERO: con todo en orden SI se puede.
    expect(puedePublicar({ estado: "propuesto" }, true)).toBe(true);
    expect(puedePublicar({ estado: "propuesto" }, false)).toBe(false);
    expect(puedePublicar({ estado: "publicado" }, true)).toBe(false);
    expect(puedePublicar({ estado: "descartado" }, true)).toBe(false);
  });

  it("8 — sin credenciales es accionable y dice QUE falta", () => {
    const r = resumenCalendario("sin_credenciales");
    expect(r.accionable).toBe(true);
    expect(r.texto).toContain("identificador");
    expect(r.texto).toContain("Microsoft");

    // GUARD: un estado sano NO es accionable, o "accionable" no significaria nada.
    expect(resumenCalendario("ok").accionable).toBe(false);
    expect(resumenCalendario("apagado").accionable).toBe(false);
    expect(resumenCalendario("error").accionable).toBe(true);
    // Ningun estado devuelve texto vacio.
    for (const e of ["ok", "apagado", "sin_credenciales", "error", "loquesea"]) {
      expect(resumenCalendario(e).texto.length).toBeGreaterThan(0);
    }
  });

  it("9 — K3: las 4 acciones del ciclo, siempre presentes y sin salir de la pantalla", () => {
    const conTodo = accionesDisponibles(fila(), { publishOn: true });
    expect(conTodo).toHaveLength(4);
    expect(conTodo.map((a) => a.id)).toEqual([
      "importar",
      "regenerar",
      "publicar",
      "actualizar",
    ]);
    // NINGUNA lleva a otra seccion: el ciclo entero pasa en UNA sola pantalla.
    expect(conTodo.every((a) => a.navPath === null)).toBe(true);
    expect(conTodo.find((a) => a.id === "publicar")!.habilitada).toBe(true);

    // Con la publicacion apagada la accion SIGUE ESTANDO, deshabilitada. Una
    // accion que desaparece deja al operador sin saber que existe.
    const sinPublicar = accionesDisponibles(fila(), { publishOn: false });
    expect(sinPublicar).toHaveLength(4);
    const publicar = sinPublicar.find((a) => a.id === "publicar")!;
    expect(publicar).toBeDefined();
    expect(publicar.habilitada).toBe(false);
    expect(publicar.navPath).toBeNull();
  });
});

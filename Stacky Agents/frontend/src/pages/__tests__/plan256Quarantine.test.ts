/**
 * Plan 256 F3 — tests del nucleo PURO de la tarjeta "Artefactos en cuarentena".
 *
 * Restriccion dura de la casa: `@testing-library/react` y `jsdom` NO estan
 * instalados, asi que el componente React no se testea. Toda la logica que
 * merece un test vive en un modulo puro (`src/incidents/quarantineModel.ts`) y
 * el componente queda como cascara de render.
 *
 * Correr POR ARCHIVO con ruta concreta (contaminacion cross-file conocida):
 *   npx vitest run src/pages/__tests__/plan256Quarantine.test.ts
 */
import { describe, expect, it } from "vitest";

import {
  formatAge,
  shouldRenderCard,
  sortByAgeDesc,
  type QuarantineItem,
} from "../../incidents/quarantineModel";

function item(path: string, ageDays: number): QuarantineItem {
  return {
    path,
    reason: "intake rechazo el artefacto: el archivo esta vacio o solo tiene espacios.",
    mtime_ns: 1785000000000000000,
    file_name: "pending-task.json",
    cause_code: "INTAKE_EMPTY",
    first_seen: "2026-07-16T13:34:24.000000Z",
    age_days: ageDays,
    occurrences: 25,
    has_original_backup: false,
    discarded: false,
    retryable: true,
  };
}

describe("plan 256 — tarjeta de artefactos en cuarentena", () => {
  it("no renderiza si count es cero", () => {
    expect(shouldRenderCard(0)).toBe(false);
    expect(shouldRenderCard(1)).toBe(true);
    expect(shouldRenderCard(25)).toBe(true);
    // Defensivo: un backend viejo puede no mandar el campo.
    expect(shouldRenderCard(undefined as unknown as number)).toBe(false);
    expect(shouldRenderCard(-1)).toBe(false);
  });

  it("formatea la antiguedad en dias", () => {
    const ahora = "2026-07-26T13:34:24.000000Z";
    expect(formatAge("2026-07-16T13:34:24.000000Z", ahora)).toBe("atascado hace 10 dias");
    expect(formatAge("2026-07-25T13:34:24.000000Z", ahora)).toBe("atascado hace 1 dia");
    expect(formatAge("2026-07-26T10:00:00.000000Z", ahora)).toBe("detectado hoy");
    expect(formatAge(null, ahora)).toBe("antiguedad desconocida");
    expect(formatAge("no-es-una-fecha", ahora)).toBe("antiguedad desconocida");
    // El sufijo Z sin microsegundos tambien tiene que parsear.
    expect(formatAge("2026-07-16T13:34:24Z", ahora)).toBe("atascado hace 10 dias");
  });

  it("ordena por antiguedad descendente", () => {
    const original = [item("b", 2), item("a", 11), item("c", 0)];
    const ordenado = sortByAgeDesc(original);

    expect(ordenado.map((i) => i.path)).toEqual(["a", "b", "c"]);
    // No muta la lista que le pasan.
    expect(original.map((i) => i.path)).toEqual(["b", "a", "c"]);
    // Empate: desempata por ruta, para que el orden sea estable entre refrescos.
    expect(sortByAgeDesc([item("z", 3), item("x", 3)]).map((i) => i.path)).toEqual(["x", "z"]);
  });
});

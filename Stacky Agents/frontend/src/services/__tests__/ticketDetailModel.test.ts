// frontend/src/services/__tests__/ticketDetailModel.test.ts — Plan 287 F4
//
// Los 9 tests son las 9 reglas de comportamiento del modulo puro de navegacion
// de la ficha. En este repositorio NO estan instalados @testing-library/react ni
// jsdom, asi que toda la logica testeable vive en .ts puro y el .tsx queda tonto
// (mismo reparto que uso el plan 265 con sus services/console*.ts).
//
// La regla 9 (v2/C6) es la que distingue "el arbol todavia no cargo" de "el arbol
// cargo y este ticket no esta": sin ella, pasarle a la ficha el arbol FILTRADO por
// "mias" da tres listas vacias mudas en vez de un mensaje.

import { describe, it, expect } from "vitest";
import {
  construirNavegacion,
  aplanarJerarquia,
  etiquetaDeSalto,
  MAX_SALTOS_JERARQUIA,
} from "../ticketDetailModel";
import type { TicketHierarchy, TicketNode } from "../../types";

// ── Fabrica de nodos: lo minimo de Ticket + children ─────────────────────────

function nodo(
  ado_id: number,
  extra: Partial<TicketNode> = {},
  children: TicketNode[] = [],
): TicketNode {
  return {
    id: ado_id,
    ado_id,
    project: "grupo/proyecto",
    title: `Ticket ${ado_id}`,
    work_item_type: "Task",
    ado_state: "New",
    ...extra,
    children,
  } as TicketNode;
}

/**  epica 10
 *    ├── 42 (padre de 77)
 *    │     └── 77
 *    └── 43
 *   orphans: 99 (con motivo)
 */
function arbol(): TicketHierarchy {
  const n77 = nodo(77);
  const n42 = nodo(42, {}, [n77]);
  const n43 = nodo(43);
  const epica = nodo(10, { work_item_type: "Epic" }, [n42, n43]);
  const huerfano = nodo(99, { motivo_huerfano: "el padre 500 no esta en el tablero" });
  return { epics: [epica], orphans: [huerfano] };
}

describe("ticketDetailModel (plan 287 F4)", () => {
  it("navegacion_arbol_vacio", () => {
    for (const vacio of [undefined, null]) {
      const nav = construirNavegacion(vacio, 42);
      expect(nav.foco).toBeNull();
      expect(nav.cadenaAncestros).toEqual([]);
      expect(nav.hijos).toEqual([]);
      expect(nav.hermanos).toEqual([]);
      expect(nav.motivoHuerfano).toBeNull();
      // Regla 9: sin arbol NO es "esta fuera del arbol", es "todavia no se".
      expect(nav.focoFueraDelArbol).toBe(false);
    }
  });

  it("navegacion_foco_epica", () => {
    const nav = construirNavegacion(arbol(), 10);
    expect(nav.foco?.ado_id).toBe(10);
    expect(nav.cadenaAncestros).toEqual([]);
    expect(nav.hijos.map((h) => h.ado_id)).toEqual([42, 43]);
    expect(nav.hermanos).toEqual([]);
  });

  it("navegacion_foco_hijo_directo", () => {
    const nav = construirNavegacion(arbol(), 42);
    expect(nav.foco?.ado_id).toBe(42);
    expect(nav.cadenaAncestros.map((a) => a.ado_id)).toEqual([10]);
    // los otros hijos de la epica, SIN el foco
    expect(nav.hermanos.map((h) => h.ado_id)).toEqual([43]);
    expect(nav.hijos.map((h) => h.ado_id)).toEqual([77]);
  });

  it("navegacion_foco_nieto", () => {
    const nav = construirNavegacion(arbol(), 77);
    // raiz primero
    expect(nav.cadenaAncestros.map((a) => a.ado_id)).toEqual([10, 42]);
    expect(nav.hermanos).toEqual([]);   // 42 no tiene otros hijos
    expect(nav.hijos).toEqual([]);
  });

  it("navegacion_foco_huerfano_expone_motivo", () => {
    const nav = construirNavegacion(arbol(), 99);
    expect(nav.foco?.ado_id).toBe(99);
    expect(nav.cadenaAncestros).toEqual([]);
    expect(nav.hermanos).toEqual([]);
    expect(nav.motivoHuerfano).toBe("el padre 500 no esta en el tablero");
    // Y un nodo colgado NO trae motivo (el servidor solo lo emite en orphans).
    expect(construirNavegacion(arbol(), 42).motivoHuerfano).toBeNull();
  });

  it("navegacion_foco_ausente_no_lanza", () => {
    const nav = construirNavegacion(arbol(), 123456);
    expect(nav.foco).toBeNull();
    expect(nav.cadenaAncestros).toEqual([]);
    expect(nav.hijos).toEqual([]);
    expect(nav.hermanos).toEqual([]);
  });

  it("aplanar_corta_ante_ciclo", () => {
    // Ciclo artificial: un nodo que se declara hijo de si mismo.
    const ciclo = nodo(1);
    ciclo.children = [ciclo];
    const jerarquia: TicketHierarchy = { epics: [ciclo], orphans: [] };

    const planos = aplanarJerarquia(jerarquia);

    expect(planos.length).toBeGreaterThan(0);
    expect(planos.length).toBeLessThanOrEqual(MAX_SALTOS_JERARQUIA);
    // Y no cuelga ni repite: el nodo aparece UNA sola vez.
    expect(planos.filter((n) => n.ado_id === 1).length).toBe(1);
  });

  it("etiqueta_omite_campos_ausentes", () => {
    expect(etiquetaDeSalto({ ado_id: 1234, work_item_type: "Historia", ado_state: "En curso" }))
      .toBe("1234 · Historia · En curso");
    // Sin tipo ni estado: NO imprime "undefined" ni separadores sueltos.
    const parcial = etiquetaDeSalto({ ado_id: 7, work_item_type: undefined, ado_state: undefined });
    expect(parcial).toBe("7");
    expect(parcial).not.toContain("undefined");
    expect(parcial).not.toContain("·");
    expect(etiquetaDeSalto({ ado_id: 8, work_item_type: "Bug", ado_state: undefined }))
      .toBe("8 · Bug");
  });

  it("navegacion_distingue_arbol_sin_cargar_de_foco_ausente", () => {
    // (v2/C6) Arbol PRESENTE pero sin el foco => true. Es el caso del arbol
    // filtrado por "mias": el hermano ajeno no esta y hay que DECIRLO.
    expect(construirNavegacion(arbol(), 123456).focoFueraDelArbol).toBe(true);
    // Un arbol cargado y VACIO tambien cuenta como cargado.
    expect(construirNavegacion({ epics: [], orphans: [] }, 42).focoFueraDelArbol).toBe(true);
    // Arbol sin cargar => false (todavia no se, no es lo mismo).
    expect(construirNavegacion(undefined, 42).focoFueraDelArbol).toBe(false);
    expect(construirNavegacion(null, 42).focoFueraDelArbol).toBe(false);
    // Foco presente => false.
    expect(construirNavegacion(arbol(), 42).focoFueraDelArbol).toBe(false);
  });
});

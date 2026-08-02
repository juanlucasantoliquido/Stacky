// frontend/src/services/ticketDetailModel.ts — Plan 287 F4
//
// Deriva padre, cadena de ancestros, hijos y hermanos del arbol que el tablero YA
// tiene cacheado. Modulo PURO: no hace red, no muta, no toca window. La ficha
// (.tsx) queda tonta porque en este repositorio no estan instalados
// @testing-library/react ni jsdom y un componente no se puede montar en una prueba.
//
// v2/C6 — REGLA DURA: la ficha recibe el arbol CRUDO (`hierarchy`), nunca el
// filtrado por "mias" (`displayHierarchy`). Una ficha que oculta la mitad del
// arbol miente: un hijo o un hermano de otra persona no estaria en el arbol y la
// navegacion moriria en silencio. Cuando el arbol vino pero no contiene al foco,
// `focoFueraDelArbol` lo dice para que la columna lo ESCRIBA en vez de mostrar
// tres listas vacias.

import type { Ticket, TicketNode, TicketHierarchy } from "../types";

/** Espejo del tope del servidor (api/tickets.py) para no colgarse ante un ciclo. */
export const MAX_SALTOS_JERARQUIA = 50;

export interface NavegacionJerarquia {
  /** Del ancestro mas lejano al padre directo. Vacio si el foco no tiene padre. */
  cadenaAncestros: TicketNode[];
  /** Hijos directos del foco, en el orden en que vienen del servidor. */
  hijos: TicketNode[];
  /** Otros hijos del mismo padre, EXCLUYENDO al foco. Vacio si no tiene padre. */
  hermanos: TicketNode[];
  /** El nodo del foco dentro del arbol, o null si el arbol no lo contiene. */
  foco: TicketNode | null;
  /** Motivo textual que el servidor ya calcula cuando el ticket quedo suelto. */
  motivoHuerfano: string | null;
  /** v2/C6 — true si el arbol vino cargado pero NO contiene al foco. Distingue
   *  "todavia no cargo" de "cargo y este ticket no esta": la ficha tiene que
   *  DECIRLO, no mostrar tres listas vacias. */
  focoFueraDelArbol: boolean;
}

const VACIA: NavegacionJerarquia = {
  cadenaAncestros: [],
  hijos: [],
  hermanos: [],
  foco: null,
  motivoHuerfano: null,
  focoFueraDelArbol: false,
};

/** Raices del arbol: las epicas y los huerfanos. */
function raices(jerarquia: TicketHierarchy): TicketNode[] {
  return [...(jerarquia.epics ?? []), ...(jerarquia.orphans ?? [])];
}

/** Todos los nodos del arbol, aplanados, sin repetir, con tope de saltos. */
export function aplanarJerarquia(
  jerarquia: TicketHierarchy | undefined | null,
): TicketNode[] {
  if (!jerarquia) return [];
  const vistos = new Set<TicketNode>();
  const planos: TicketNode[] = [];
  const pila: TicketNode[] = [...raices(jerarquia)];

  while (pila.length > 0 && planos.length < MAX_SALTOS_JERARQUIA) {
    const actual = pila.shift() as TicketNode;
    if (!actual || vistos.has(actual)) continue;   // corta el ciclo por identidad
    vistos.add(actual);
    planos.push(actual);
    for (const hijo of actual.children ?? []) pila.push(hijo);
  }
  return planos;
}

/** Camino desde una raiz hasta el nodo con ese ado_id. Vacio si no esta. */
function caminoHasta(raiz: TicketNode, ado_id: number, profundidad = 0): TicketNode[] {
  if (profundidad > MAX_SALTOS_JERARQUIA) return [];
  if (raiz.ado_id === ado_id) return [raiz];
  for (const hijo of raiz.children ?? []) {
    if (hijo === raiz) continue;                   // ciclo directo declarado
    const resto = caminoHasta(hijo, ado_id, profundidad + 1);
    if (resto.length > 0) return [raiz, ...resto];
  }
  return [];
}

/** Deriva la navegacion del foco desde el arbol cacheado. NO hace red. NO muta. */
export function construirNavegacion(
  jerarquia: TicketHierarchy | undefined | null,
  ticketId: number,
): NavegacionJerarquia {
  if (!jerarquia) return { ...VACIA };            // regla 1: nunca lanza

  let camino: TicketNode[] = [];
  for (const raiz of raices(jerarquia)) {
    camino = caminoHasta(raiz, ticketId);
    if (camino.length > 0) break;
  }

  // regla 6 + regla 9: el arbol vino, pero el foco no esta.
  if (camino.length === 0) return { ...VACIA, focoFueraDelArbol: true };

  const foco = camino[camino.length - 1];
  const cadenaAncestros = camino.slice(0, -1);    // raiz primero, padre al final
  const padre = cadenaAncestros[cadenaAncestros.length - 1] ?? null;

  return {
    cadenaAncestros,
    hijos: [...(foco.children ?? [])],
    hermanos: padre ? (padre.children ?? []).filter((h) => h !== foco) : [],
    foco,
    // regla 5: el servidor solo emite el motivo en `orphans`.
    motivoHuerfano: foco.motivo_huerfano ?? null,
    focoFueraDelArbol: false,
  };
}

/** Etiqueta corta para un salto de navegacion: "1234 · Historia · En curso". */
export function etiquetaDeSalto(
  t: Pick<Ticket, "ado_id" | "work_item_type" | "ado_state">,
): string {
  // regla 8: lo ausente se OMITE, no se imprime como "undefined".
  return [t.ado_id, t.work_item_type, t.ado_state]
    .map((p) => (p == null ? "" : String(p).trim()))
    .filter((p) => p.length > 0)
    .join(" · ");
}

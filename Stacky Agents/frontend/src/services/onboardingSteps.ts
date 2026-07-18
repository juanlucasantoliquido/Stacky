/**
 * Plan 151 F1 — Pasos del tour como data pura + lista blanca de anclas.
 *
 * Cada `target` que sea un selector data-tour DEBE apuntar a un ancla declarada
 * en DECLARED_ANCHORS (verificado por el test `stepAnchorsAreDeclared` de F1).
 * Los pasos "conceptuales" usan `target: null` (card centrada por diseño).
 */

export type StepPosition = "center" | "right" | "bottom" | "left" | "top";

export interface TourStep {
  id: string;
  /** Selector data-tour o null (card centrada sin spotlight). */
  target: string | null;
  title: string;
  body: string;
  position: StepPosition;
}

// Anclas NORMATIVAS que F2/F3 declaran físicamente en el DOM:
//   nav            -> <nav> de la navegación principal (App.tsx)
//   topbar-actions -> <div styles.actions> de la TopBar
//   help-launcher  -> IconButton "?" (HelpLauncher, dentro de topbar-actions)
export const DECLARED_ANCHORS = ["nav", "topbar-actions", "help-launcher"] as const;

export const STEPS: TourStep[] = [
  {
    id: "welcome",
    target: null,
    position: "center",
    title: "Bienvenido a Stacky Agents",
    body: "Tu equipo de agentes IA para cerrar tickets más rápido. Te muestro el mapa en 5 pasos. Podés saltarlo cuando quieras (Esc).",
  },
  {
    id: "nav",
    target: '[data-tour="nav"]',
    position: "right",
    title: "El mapa: la navegación",
    body: "Acá están todas las superficies: tu Equipo, Tickets, Configuración, Diagnóstico y más. Cada una es una capacidad distinta.",
  },
  {
    id: "project",
    target: '[data-tour="topbar-actions"]',
    position: "bottom",
    title: "Tu proyecto y estado",
    body: "Arriba a la derecha ves el proyecto activo, la versión y si hay agentes trabajando. Cambiá de proyecto desde el selector de la izquierda.",
  },
  {
    id: "palette",
    target: null,
    position: "center",
    title: "Ctrl+K es tu atajo",
    body: "Apretá Ctrl+K en cualquier momento para buscar tickets, agentes o saltar entre pantallas con el teclado.",
  },
  {
    id: "help",
    target: '[data-tour="help-launcher"]',
    position: "bottom",
    title: "¿Perdido? Este botón",
    body: "Este signo de pregunta re-abre este tour cuando quieras. No molesta: solo aparece si lo pedís.",
  },
  {
    id: "done",
    target: null,
    position: "center",
    title: "Listo, explorá",
    body: "Eso es todo. Nada de esto ejecuta acciones por vos: Stacky siempre te deja decidir. ¡A trabajar!",
  },
];

import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { describe, it, expect } from "vitest";

/**
 * Plan 288 F1 — la superficie de clasificacion local no se ve en la vista de tickets.
 *
 * DOS PATAS EN EL MISMO TEST, a proposito: un assert de AUSENCIA pasa solo si el
 * archivo no existe o si la ruta esta mal. La pata de PRESENCIA lo prueba vivo.
 */
const leer = (rel: string) => {
  const p = join(process.cwd(), rel);
  expect(existsSync(p), `no existe ${rel} — la ruta del test está mal, no es que el símbolo se fue`).toBe(true);
  return readFileSync(p, "utf-8");
};

const TABLERO = "src/pages/TicketBoard.tsx";
const GRAFO = "src/components/TicketGraphView.jsx";

describe("Plan 288 F1 — la vista del ticket no muestra la clasificación local", () => {
  it("el tablero no monta ni importa los controles de clasificación, y SÍ conserva sus 4 acciones", () => {
    const src = leer(TABLERO);
    // AUSENCIA
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain("<PublicarEtiquetasGitLab");
    expect(src).not.toContain('from "../components/JerarquiaLocalControl"');
    expect(src).not.toContain('from "../components/PublicarEtiquetasGitLab"');
    // PRESENCIA — en el MISMO test: si esto falla, el archivo se vació o se rompió
    expect(src).toContain("<FinishWorkButton");
    expect(src).toContain("<CreateChildTaskButton");
    expect(src).toContain("<TicketLocalInsightButton");
    expect(src).toContain("<RecoverExecutionButton");
  });

  it("el grafo no monta ni importa el control de clasificación, y SÍ conserva sus acciones", () => {
    const src = leer(GRAFO);
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain('from "./JerarquiaLocalControl"');
    expect(src).toContain("<FinishWorkButton");
    expect(src).toContain("<CreateChildTaskButton");
    expect(src).toContain("<RecoverExecutionButton");
  });

  it("el motor de datos NO se borró: la lógica pura sigue exportada y con sus consumidores", () => {
    const motor = leer("src/lib/jerarquiaLocal.ts");
    expect(motor).toContain("export function debeMostrarControlJerarquia");
    expect(motor).toContain("export function validarPadre");
    expect(motor).toContain("export function esPublicable");
    expect(motor).toContain("export const TIPOS_CANONICOS_JERARQUIA");
    // Y las claves del contrato del servidor siguen viajando en el tipo del ticket.
    expect(leer("src/types.ts")).toContain("local_work_item_type");
    expect(leer("src/types.ts")).toContain("local_parent_iid");
    // Los dos componentes SIGUEN EXISTIENDO: este plan los desmonta, no los borra.
    expect(existsSync(join(process.cwd(), "src/components/JerarquiaLocalControl.tsx"))).toBe(true);
    expect(existsSync(join(process.cwd(), "src/components/PublicarEtiquetasGitLab.tsx"))).toBe(true);
  });

  // ── Plan 288 F3 — rama 287-PRESENTE ───────────────────────────────────────
  // El disparador mecánico de §6.F3 (`Test-Path src/components/ticket/TicketFullView.tsx`)
  // dio TRUE al implementar este plan: el 287 ya estaba construido en el árbol.
  //
  // DESVIACIÓN DECLARADA respecto del texto de §6.F3: el plan proponía
  // `expect(src).toContain("<FinishWorkButton")` como pata de presencia, pero la
  // ficha del 287 NO monta FinishWorkButton — es un diálogo de navegación,
  // comentarios y adjuntos. Usar ese símbolo habría dejado la pata de presencia
  // roja para siempre. Se ancla en los símbolos que la ficha SÍ tiene y que
  // prueban que sigue siendo la ficha (el diálogo y el enlace al tracker).
  it("la ficha a pantalla completa tampoco monta los controles de clasificación", () => {
    const src = leer("src/components/ticket/TicketFullView.tsx");
    // AUSENCIA
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain("<PublicarEtiquetasGitLab");
    expect(src).not.toContain("JerarquiaLocalControl");
    expect(src).not.toContain("PublicarEtiquetasGitLab");
    // PRESENCIA: la ficha sigue siendo la ficha.
    expect(src).toContain("<Dialog");
    expect(src).toContain("<TrackerDeepLink");
  });
});

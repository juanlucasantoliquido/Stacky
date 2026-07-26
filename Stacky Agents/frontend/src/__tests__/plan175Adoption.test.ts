// Plan 175 F5 — Verificación transversal de la serie del cockpit.
//
// Los tests de modelo pasarían igual aunque nada estuviera cableado. Esto lee
// los archivos y exige que el cableado exista — y, sobre todo, que los
// invariantes de seguridad no se hayan aflojado de pasada.
import fs from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";

import { actionsForExecution, quickActions } from "../services/entityActions";
import type { ExecutionHistoryItem } from "../api/endpoints";

const SRC = path.resolve(__dirname, "..");

function leer(rel: string): string {
  return fs.readFileSync(path.join(SRC, rel), "utf-8");
}

describe("Plan 175 — adopción cableada", () => {
  it("el historial monta peek, menú contextual y acciones rápidas", () => {
    const s = leer("pages/ExecutionHistoryPage.tsx");

    expect(s).toContain("<PeekCard");
    expect(s).toContain("<ContextMenu");
    expect(s).toContain("quickActions(");
  });

  it("las tres superficies consumen el MISMO registro", () => {
    // Si cada una armara su lista, ofrecerían cosas distintas para la misma
    // entidad y el operador dejaría de confiar en lo que ve.
    const s = leer("pages/ExecutionHistoryPage.tsx");

    expect(s).toContain("actionsForExecution(");
  });

  it("cada capacidad tiene su gate", () => {
    const s = leer("pages/ExecutionHistoryPage.tsx");

    expect(s).toContain("ui_peek_enabled");
    expect(s).toContain("ui_context_menu_enabled");
  });

  it("el copiado pasa por el servicio canónico, no por writeText crudo", () => {
    // Una llamada cruda nueva rompería el ratchet del plan 194.
    const s = leer("services/clipboard.ts");

    expect(s).toContain("copyService");
    expect(s).not.toContain("navigator.clipboard");
  });

  it("los overlays van por portal: no pueden romper el layout de la tabla", () => {
    for (const p of ["components/peek/PeekCard.tsx", "components/contextmenu/ContextMenu.tsx"]) {
      expect(leer(p)).toContain("createPortal");
    }
  });

  it("la tarjeta de peek NUNCA pide el foco", () => {
    // Robárselo a quien está tipeando sería peor que no mostrar nada.
    expect(leer("components/peek/PeekCard.tsx")).not.toContain(".focus(");
  });
});

describe("Plan 175 — invariantes de seguridad", () => {
  const estados = ["running", "completed", "failed", "cancelled"];

  it("NINGUNA acción con efecto es quick, en ningún estado", () => {
    for (const status of estados) {
      const acciones = actionsForExecution({ id: 1, status } as ExecutionHistoryItem, "http://x");
      const rapidas = quickActions(acciones);

      expect(rapidas.every((a) => a.effect === "safe")).toBe(true);
      // Y las destructivas nunca aparecen entre las rápidas.
      expect(rapidas.some((a) => a.id === "exec-delete")).toBe(false);
      expect(rapidas.some((a) => a.id === "exec-cancel")).toBe(false);
    }
  });

  it("el armado en dos pasos sigue siendo el mecanismo de confirmación", () => {
    const s = leer("components/contextmenu/ContextMenu.tsx");

    expect(s).toContain("armTransition");
    // Los diálogos nativos bloquean el hilo y el arnés no puede verlos.
    expect(s).not.toContain("window.confirm");
  });
});

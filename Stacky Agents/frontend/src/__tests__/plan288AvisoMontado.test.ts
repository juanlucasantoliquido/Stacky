import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { describe, it, expect } from "vitest";

/**
 * Plan 288 F9 — el aviso de origen del catálogo está en las 4 superficies de
 * selección de modelo.
 *
 * POR QUE NO SE MIDE CON `grep | wc -l`: eso cuenta LINEAS. El `import` y el uso
 * en el MISMO archivo ya suman 2, así que un umbral de 4 se alcanzaba montando
 * el aviso en apenas DOS archivos. Acá se verifica archivo por archivo, POR
 * NOMBRE, que es lo único que prueba lo que se quiere probar.
 */
const leer = (rel: string) => {
  const p = join(process.cwd(), rel);
  expect(existsSync(p), `no existe ${rel} — la ruta del test está mal`).toBe(true);
  return readFileSync(p, "utf-8");
};

const SUPERFICIES = [
  "src/components/EpicFromBriefModal.tsx",
  "src/components/IncidentResolverModal.tsx",
  "src/pages/PlansBoardPage.tsx",
  "src/pages/TicketBoard.tsx",
];

describe("Plan 288 F9 — el aviso está montado donde se elige el modelo", () => {
  it.each(SUPERFICIES)("%s monta el aviso Y conserva el selector", (ruta) => {
    const src = leer(ruta);
    // DOS PATAS: si el archivo perdió el selector, el aviso solo no significa nada.
    expect(src).toContain("<AvisoCatalogoModelos");
    expect(src).toContain("useModelCatalog");
  });

  it("el componente del aviso existe y es tonto (la decisión vive en el .ts puro)", () => {
    const src = leer("src/components/AvisoCatalogoModelos.tsx");
    expect(src).toContain("describirOrigenCatalogo");
    expect(src).toContain("useModelCatalog");
  });

  it("AUSENCIA — ModelDecisionChip NO monta el aviso: no es un selector", () => {
    const src = leer("src/components/ModelDecisionChip.tsx");
    expect(src).not.toContain("<AvisoCatalogoModelos");
    // PRESENCIA en el mismo test: el archivo sigue siendo el indicador que era.
    expect(src).toContain("useModelCatalog");
  });
});

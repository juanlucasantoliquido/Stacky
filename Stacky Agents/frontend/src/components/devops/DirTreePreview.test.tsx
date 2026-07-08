/**
 * Tests de componente para DirTreePreview (Plan 107 F4).
 *
 * NOTA (bloqueo de entorno, no de código): este checkout NO tiene instalado
 * @testing-library/react ni jsdom (node_modules sin esas carpetas, verificado
 * antes de escribir este archivo). Es una condición PREEXISTENTE de TODO el
 * repo -- src/components/__tests__/CreateChildTaskButton.test.tsx y
 * HarnessFlagsPanel.test.tsx fallan con el MISMO "Cannot find package
 * '@testing-library/react'" incluso sin tocar nada de Plan 107. Este archivo
 * se escribe igual (test-first, mismo patrón que esos .test.tsx existentes)
 * para quedar listo apenas se instale la dependencia; hasta entonces la
 * fase F4 se reporta BLOQUEADA para esta suite puntual, no oculta.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DirTreePreview } from "./DirTreePreview";
import type { PlanEntry } from "../../devops/environmentModel";

function entry(path: string, status: PlanEntry["status"]): PlanEntry {
  return { path, status, reason: status === "unsafe" ? "fuera_de_root" : null };
}

describe("DirTreePreview", () => {
  it("renders nested folders from flat entries", () => {
    render(
      <DirTreePreview
        entries={[entry("a", "to_create"), entry("a/b", "to_create")]}
        rootLabel="C:\\ambientes\\pacifico"
      />
    );
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
  });

  it('shows "nuevo" badge on to_create nodes', () => {
    render(
      <DirTreePreview
        entries={[entry("nueva", "to_create"), entry("vieja", "exists_ok")]}
        rootLabel="C:\\raiz"
      />
    );
    expect(screen.getByText(/nuevo/i)).toBeInTheDocument();
  });

  it("collapse hides children", () => {
    render(
      <DirTreePreview
        entries={[entry("a", "to_create"), entry("a/b", "to_create")]}
        rootLabel="C:\\raiz"
      />
    );
    // depth 0 expandido por default -> 'b' visible de entrada.
    expect(screen.getByText("b")).toBeInTheDocument();
    fireEvent.click(screen.getByText("a"));
    expect(screen.queryByText("b")).not.toBeInTheDocument();
  });

  it('filter "solo nuevas" hides exists_ok-only subtrees', () => {
    render(
      <DirTreePreview
        entries={[entry("nueva/x", "to_create"), entry("vieja/y", "exists_ok")]}
        rootLabel="C:\\raiz"
      />
    );
    expect(screen.getByText("nueva")).toBeInTheDocument();
    expect(screen.getByText("vieja")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Solo nuevas"));
    expect(screen.getByText("nueva")).toBeInTheDocument();
    expect(screen.queryByText("vieja")).not.toBeInTheDocument();
  });

  it("shows SANDBOX badge when sandboxActive", () => {
    render(
      <DirTreePreview
        entries={[entry("a", "to_create")]}
        rootLabel="C:\\sandbox"
        sandboxActive
      />
    );
    expect(screen.getByText(/SANDBOX/i)).toBeInTheDocument();
  });

  it("does not show SANDBOX badge when sandboxActive is false", () => {
    render(
      <DirTreePreview
        entries={[entry("a", "to_create")]}
        rootLabel="C:\\prod"
        sandboxActive={false}
      />
    );
    expect(screen.queryByText(/SANDBOX/i)).not.toBeInTheDocument();
  });
});

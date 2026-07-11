/**
 * Tests de componente para RemoteConsoleSection (fix reactividad Plan 105).
 *
 * REGRESIÓN CUBIERTA (reportada por el operador 2026-07-09): "cuando selecciono
 * un servidor NO me figura la consola". Causa raíz: el `selectedServer` interno
 * era un useState inicializado una sola vez desde `ctx.selectedServer?.alias` en
 * el montaje (setter nunca invocado), así que al cambiar de servidor con la
 * sección YA montada, ctx cambiaba pero el estado interno quedaba en null y el
 * componente se congelaba en "Selecciona un servidor...". El fix deriva
 * `selectedServer` directamente de ctx en cada render.
 *
 * Este test prueba la REACTIVIDAD: mismo componente montado, primero sin
 * servidor (placeholder) y luego, tras un rerender con ctx.selectedServer
 * seteado, debe mostrar el header "Consola: <alias>".
 *
 * NOTA DE ENTORNO (bloqueo preexistente, NO introducido por este cambio): este
 * checkout no tiene instalados `@testing-library/react` ni un entorno jsdom
 * (verificado: node_modules/@testing-library ausente, jsdom ausente, vite.config
 * sin bloque `test.environment`). Es el MISMO gap que bloquea a
 * DirTreePreview.test.tsx y ActiveRunsPanel.test.tsx. El test queda escrito
 * test-first, listo para correr apenas se resuelva el gap de entorno. La
 * verificación de tipos (tsc --noEmit) sí corre y cubre el fix.
 */
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import type { ReactElement } from "react";
import { RemoteConsoleSection } from "./RemoteConsoleSection";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";

// Evitar llamadas de red reales de las queries WinRM/conversaciones.
vi.mock("../../api/endpoints", () => ({
  DevOpsRemoteConsole: {
    checkWinrm: vi.fn().mockResolvedValue({ ok: true }),
    getConversations: vi.fn().mockResolvedValue([]),
    getAudit: vi.fn().mockResolvedValue([]),
    exec: vi.fn(),
    createConversation: vi.fn(),
    setWriteMode: vi.fn(),
  },
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function ctxWith(selectedAlias: string | null): DevOpsSectionContext {
  const servers = [{ alias: "srv1", host: "10.0.0.1" }];
  return {
    health: {
      flag_enabled: true,
      generator_enabled: false,
      trigger_enabled: false,
      remote_console_enabled: true,
    },
    refetchHealth: () => {},
    servers,
    selectedServer: selectedAlias
      ? servers.find((s) => s.alias === selectedAlias) ?? null
      : null,
  };
}

describe("RemoteConsoleSection reactividad al servidor seleccionado", () => {
  it("muestra el placeholder cuando no hay servidor seleccionado", () => {
    render(wrap(<RemoteConsoleSection ctx={ctxWith(null)} />));
    expect(
      screen.getByText(/Selecciona un servidor para usar la consola remota/i)
    ).toBeInTheDocument();
  });

  it("al seleccionar un servidor (rerender con ctx nuevo) aparece la consola", () => {
    const { rerender } = render(wrap(<RemoteConsoleSection ctx={ctxWith(null)} />));
    // Estado inicial: placeholder, sin header de consola.
    expect(screen.queryByText(/Consola: srv1/)).not.toBeInTheDocument();

    // El operador selecciona "srv1" en el selector global → ctx cambia.
    rerender(wrap(<RemoteConsoleSection ctx={ctxWith("srv1")} />));

    // La consola DEBE aparecer (con el fix). Con el bug quedaba en el placeholder.
    expect(screen.getByText(/Consola: srv1/)).toBeInTheDocument();
  });
});

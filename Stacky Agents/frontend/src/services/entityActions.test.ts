// Plan 175 F1 — Registro de acciones por entidad.
import { describe, it, expect, vi } from "vitest";
import {
  actionsForExecution,
  actionsForTicket,
  quickActions,
  type EntityActionContext,
} from "./entityActions";
import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";

function exec(over: Partial<ExecutionHistoryItem> = {}): ExecutionHistoryItem {
  return { id: 7, status: "completed", ...over } as ExecutionHistoryItem;
}

function ticket(over: Partial<Ticket> = {}): Ticket {
  return { id: 1, ado_id: 4242, project: "p", title: "Un ticket", ...over } as Ticket;
}

function ctx(over: Partial<EntityActionContext> = {}): EntityActionContext {
  return {
    copyText: vi.fn(async () => true),
    openExternal: vi.fn(),
    navigate: vi.fn(),
    askConfirm: vi.fn(async () => true),
    api: {
      cancelExecution: vi.fn(async () => ({})),
      deleteExecution: vi.fn(async () => ({})),
      publishExecution: vi.fn(async () => ({})),
    },
    onDone: vi.fn(),
    ...over,
  };
}

function ids(as: { id: string }[]): string[] {
  return as.map((a) => a.id);
}

describe("quickActions", () => {
  it("doble cerrojo: quick Y safe", () => {
    // Una acción con efecto NUNCA puede quedar a un click accidental, por más
    // que alguien la marque quick.
    const lista = [
      { id: "a", label: "", icon: "", effect: "safe" as const, quick: true, run: async () => {} },
      { id: "b", label: "", icon: "", effect: "confirm" as const, quick: true, run: async () => {} },
      { id: "c", label: "", icon: "", effect: "safe" as const, quick: false, run: async () => {} },
    ];

    expect(ids(quickActions(lista))).toEqual(["a"]);
  });

  it("ninguna acción de ejecución con efecto es quick", () => {
    for (const estado of ["running", "completed", "failed"]) {
      const conEfecto = actionsForExecution(exec({ status: estado }), "http://x").filter(
        (a) => a.effect === "confirm",
      );
      expect(conEfecto.every((a) => !a.quick)).toBe(true);
    }
  });
});

describe("actionsForExecution", () => {
  it("una ejecución en curso ofrece cancelar y NADA de borrar/publicar", () => {
    // Ofrecer algo que el backend va a rechazar no es una opción, es una
    // frustración.
    const a = ids(actionsForExecution(exec({ status: "running" }), "http://x"));

    expect(a).toContain("exec-cancel");
    expect(a).not.toContain("exec-delete");
    expect(a).not.toContain("exec-publish");
  });

  it("una completada ofrece publicar y borrar, no cancelar", () => {
    const a = ids(actionsForExecution(exec({ status: "completed" }), "http://x"));

    expect(a).toContain("exec-publish");
    expect(a).toContain("exec-delete");
    expect(a).not.toContain("exec-cancel");
  });

  it("una fallida se puede borrar pero no publicar", () => {
    const a = ids(actionsForExecution(exec({ status: "failed" }), "http://x"));

    expect(a).toContain("exec-delete");
    expect(a).not.toContain("exec-publish");
  });

  it("decir que NO corta antes de tocar la API", async () => {
    const c = ctx({ askConfirm: vi.fn(async () => false) });
    const borrar = actionsForExecution(exec(), "http://x").find((a) => a.id === "exec-delete")!;

    await borrar.run(c);

    expect(c.api.deleteExecution).not.toHaveBeenCalled();
    expect(c.onDone).not.toHaveBeenCalled();
  });

  it("decir que SÍ ejecuta y avisa", async () => {
    const c = ctx();
    const borrar = actionsForExecution(exec(), "http://x").find((a) => a.id === "exec-delete")!;

    await borrar.run(c);

    expect(c.api.deleteExecution).toHaveBeenCalledWith(7);
    expect(c.onDone).toHaveBeenCalledWith("exec-delete", true);
  });

  it("abrir usa el drawer local si lo hay, y si no navega", async () => {
    const conDrawer = ctx({ openDetail: vi.fn() });
    const sinDrawer = ctx({ openDetail: undefined });
    const abrir = (c: EntityActionContext) =>
      actionsForExecution(exec(), "http://x").find((a) => a.id === "exec-open")!.run(c);

    await abrir(conDrawer);
    await abrir(sinDrawer);

    expect(conDrawer.openDetail).toHaveBeenCalledWith(7);
    expect(sinDrawer.navigate).toHaveBeenCalled();
  });

  it("copiar el link copia un deep-link con el id", async () => {
    const c = ctx();
    const copiar = actionsForExecution(exec(), "http://x").find((a) => a.id === "exec-copy-link")!;

    await copiar.run(c);

    expect(String((c.copyText as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain("7");
  });

  it("un copiado fallido se reporta como fallido, no como éxito", async () => {
    // Decir "copiado" cuando no se copió hace que el operador pegue lo anterior.
    const c = ctx({ copyText: vi.fn(async () => false) });
    const copiar = actionsForExecution(exec(), "http://x").find((a) => a.id === "exec-copy-id")!;

    await copiar.run(c);

    expect(c.onDone).toHaveBeenCalledWith("exec-copy-id", false);
  });
});

describe("actionsForTicket", () => {
  it("con ado_url ofrece abrir y copiar el link", () => {
    const a = ids(actionsForTicket(ticket({ ado_url: "https://dev.azure.com/x/_workitems/edit/1" })));

    expect(a).toContain("ticket-open-ado");
    expect(a).toContain("ticket-copy-ado-link");
  });

  it("sin ado_url pero con id válido igual se puede abrir", () => {
    expect(ids(actionsForTicket(ticket({ ado_id: 99 })))).toContain("ticket-open-ado");
  });

  it("sin nada a dónde ir, no se ofrecen acciones externas", () => {
    const a = ids(actionsForTicket(ticket({ ado_id: 0, ado_url: undefined })));

    expect(a).not.toContain("ticket-open-ado");
    expect(a).not.toContain("ticket-copy-ado-link");
    // Pero copiar la referencia sigue teniendo sentido.
    expect(a).toContain("ticket-copy-ref");
  });

  it("la url del tracker manda sobre la construida", async () => {
    // Si el proyecto cambió de organización, la construida apunta al lugar viejo.
    const c = ctx();
    const propia = "https://otra.org/wi/5";
    const abrir = actionsForTicket(ticket({ ado_url: propia })).find((a) => a.id === "ticket-open-ado")!;

    await abrir.run(c);

    expect(c.openExternal).toHaveBeenCalledWith(propia);
  });

  it("todas las acciones de ticket son seguras", () => {
    expect(actionsForTicket(ticket()).every((a) => a.effect === "safe")).toBe(true);
  });
});

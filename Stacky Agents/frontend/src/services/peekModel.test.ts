// Plan 175 F2 — Vista previa al hover (reducer y builders).
import { describe, it, expect } from "vitest";
import {
  buildExecutionPeek,
  buildTicketPeek,
  PEEK_CLOSE_DELAY_MS,
  PEEK_IDLE,
  PEEK_OPEN_DELAY_MS,
  peekReducer,
  type PeekState,
} from "./peekModel";
import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";

const T = { kind: "execution" as const, id: 1 };
const OTRO = { kind: "execution" as const, id: 2 };

function estado(phase: PeekState["phase"], target = T): PeekState {
  return { phase, target };
}

describe("peekReducer", () => {
  it("hover arma, no abre", () => {
    const s = peekReducer(PEEK_IDLE, { type: "hover-start", target: T });

    expect(s.phase).toBe("arming");
    expect(s.target).toEqual(T);
  });

  it("irse antes del timer NUNCA abre", () => {
    // Pasar el mouse por encima camino a otro lado no puede disparar tarjetas.
    const armado = peekReducer(PEEK_IDLE, { type: "hover-start", target: T });

    expect(peekReducer(armado, { type: "hover-end" })).toEqual(PEEK_IDLE);
  });

  it("el timer abre solo si sigue armado", () => {
    expect(peekReducer(estado("arming"), { type: "open-timer" }).phase).toBe("open");
    // Un timer que llega tarde no puede abrir sobre una fila que ya nadie mira.
    expect(peekReducer(PEEK_IDLE, { type: "open-timer" })).toEqual(PEEK_IDLE);
  });

  it("el cierre es en dos tiempos", () => {
    const cerrando = peekReducer(estado("open"), { type: "hover-end" });

    expect(cerrando.phase).toBe("closing");
    expect(peekReducer(cerrando, { type: "close-timer" })).toEqual(PEEK_IDLE);
  });

  it("entrar a la tarjeta cancela el cierre", () => {
    // Si no, no se podría leerla ni copiar nada de adentro.
    expect(peekReducer(estado("closing"), { type: "card-hover" }).phase).toBe("open");
  });

  it("card-hover no abre nada si ya estaba cerrado", () => {
    expect(peekReducer(PEEK_IDLE, { type: "card-hover" })).toEqual(PEEK_IDLE);
  });

  it("pasar a otra fila re-arma para la nueva entidad", () => {
    const s = peekReducer(estado("open"), { type: "hover-start", target: OTRO });

    expect(s.phase).toBe("arming");
    expect(s.target).toEqual(OTRO);
  });

  it("Escape cierra desde cualquier fase", () => {
    for (const f of ["arming", "open", "closing"] as const) {
      expect(peekReducer(estado(f), { type: "escape" })).toEqual(PEEK_IDLE);
    }
  });

  it("las constantes están congeladas", () => {
    expect(PEEK_OPEN_DELAY_MS).toBe(400);
    expect(PEEK_CLOSE_DELAY_MS).toBe(150);
  });
});

describe("buildExecutionPeek", () => {
  const base = {
    id: 7,
    agent_type: "developer",
    agent_name: null,
    status: "completed",
    started_at: "2026-07-26T10:00:00Z",
    duration_ms: 5000,
    cost_usd: 0.12,
    tokens_in: 1000,
    tokens_out: 500,
    runtime: "codex_cli",
    model: "o4-mini",
    produced_files_count: 3,
    ticket_id: 9,
    ticket_title: "Un ticket",
    error_message: null,
  } as unknown as ExecutionHistoryItem;

  it("el título usa el nombre del agente si lo hay", () => {
    expect(buildExecutionPeek({ ...base, agent_name: "Devo" }).title).toBe("Ejecución #7 — Devo");
    expect(buildExecutionPeek(base).title).toBe("Ejecución #7 — developer");
  });

  it("los nulos se muestran como raya, no como 'null'", () => {
    const c = buildExecutionPeek({ ...base, duration_ms: null, cost_usd: null, runtime: null } as ExecutionHistoryItem);
    const valores = Object.fromEntries(c.fields.map((f) => [f.label, f.value]));

    expect(valores["Duración"]).toBe("—");
    expect(valores["Costo"]).toBe("—");
    expect(valores["Runtime"]).toBe("—");
  });

  it("sin error no aparece el campo Error", () => {
    expect(buildExecutionPeek(base).fields.some((f) => f.label === "Error")).toBe(false);
  });

  it("un error larguísimo se trunca en vez de reventar la tarjeta", () => {
    const c = buildExecutionPeek({ ...base, error_message: "x".repeat(500) } as ExecutionHistoryItem);
    const err = c.fields.find((f) => f.label === "Error")!;

    expect(err.value).toHaveLength(121);
    expect(err.value.endsWith("…")).toBe(true);
  });

  it("sin título de ticket cae al id", () => {
    const c = buildExecutionPeek({ ...base, ticket_title: null } as ExecutionHistoryItem);

    expect(c.fields.find((f) => f.label === "Ticket")!.value).toBe("#9");
  });
});

describe("buildTicketPeek", () => {
  const base = {
    id: 1,
    ado_id: 4242,
    title: "Un ticket",
    project: "p",
  } as unknown as Ticket;

  it("el título lleva la referencia del TRACKER (Plan 282 F4)", () => {
    expect(buildTicketPeek(base, "azure_devops").title).toBe("ADO-4242 — Un ticket");
    // El mismo ticket en GitLab usa la notacion que el propio GitLab muestra.
    expect(buildTicketPeek(base, "gitlab").title).toBe("#4242 — Un ticket");
    // Y el tracker del PROPIO ticket gana sobre el del proyecto.
    expect(buildTicketPeek({ ...base, tracker_type: "gitlab" } as Ticket, "azure_devops").title)
      .toBe("#4242 — Un ticket");
  });

  it("un título larguísimo se trunca", () => {
    const c = buildTicketPeek({ ...base, title: "y".repeat(200) } as Ticket);

    expect(c.title.endsWith("…")).toBe(true);
  });

  it("los campos ausentes salen como raya", () => {
    const valores = Object.fromEntries(
      buildTicketPeek(base, "azure_devops").fields.map((f) => [f.label, f.value]),
    );

    expect(valores["Tipo"]).toBe("—");
    expect(valores["Estado ADO"]).toBe("—");
    expect(valores["Asignado"]).toBe("—");

    // Plan 282 F4 — en GitLab el rotulo del campo cambia con el tracker.
    const enGitLab = Object.fromEntries(
      buildTicketPeek(base, "gitlab").fields.map((f) => [f.label, f.value]),
    );
    expect(enGitLab["Estado GitLab"]).toBe("—");
    expect(enGitLab["Estado ADO"]).toBeUndefined();
  });

  it("sin pipeline NO aparece el campo Pipeline", () => {
    // "0 etapas" en un ticket sin pipeline sugeriría que algo falló.
    expect(buildTicketPeek(base).fields.some((f) => f.label === "Pipeline")).toBe(false);
  });

  it("con pipeline resume etapas y próximo paso", () => {
    const c = buildTicketPeek({
      ...base,
      pipeline_summary: { done_stages: ["a", "b"], next_suggested: "tester" },
    } as unknown as Ticket);

    expect(c.fields.find((f) => f.label === "Pipeline")!.value).toBe("2 etapas · próx: tester");
  });
});

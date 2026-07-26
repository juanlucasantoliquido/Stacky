// Plan 175 F1 — Qué se puede hacer con una ejecución o un ticket, en un solo lugar.
//
// El registro es DATOS, no JSX: el menú contextual, las acciones rápidas inline
// y (mañana) la paleta consumen la misma lista. Si cada superficie armara la
// suya, terminarían ofreciendo cosas distintas para la misma entidad.

import type { CommandKind } from "../components/commandPaletteData";
import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";
import type { ConfirmFn } from "./confirmGateway";
import { executionDeepLink, ticketExternalLink } from "./peekLinks";
import { serializeRoute } from "./routes";

/** Reusa el vocabulario de la paleta (129) en vez de inventar otro enum. */
export type EntityKind = Extract<CommandKind, "execution" | "ticket">;

export interface EntityActionContext {
  copyText: (text: string) => Promise<boolean>;
  openExternal: (url: string) => void;
  openDetail?: (id: number) => void;
  navigate: (path: string) => void;
  /** HITL: toda acción con efecto pasa por acá. */
  askConfirm: ConfirmFn;
  api: {
    cancelExecution: (id: number) => Promise<unknown>;
    deleteExecution: (id: number) => Promise<unknown>;
    publishExecution: (id: number) => Promise<unknown>;
  };
  onDone?: (actionId: string, ok: boolean) => void;
}

export interface EntityAction {
  id: string;
  label: string;
  icon: string;
  effect: "safe" | "confirm";
  /** Candidata a aparecer inline al hover. */
  quick: boolean;
  run: (ctx: EntityActionContext) => Promise<void>;
}

/** Doble cerrojo: `quick` Y `safe`. Una acción con efecto NUNCA puede quedar a
 *  un click accidental de distancia, por más que alguien la marque quick. */
export function quickActions(actions: EntityAction[]): EntityAction[] {
  return (actions ?? []).filter((a) => a.quick && a.effect === "safe");
}

export function actionsForExecution(item: ExecutionHistoryItem, origin: string): EntityAction[] {
  const out: EntityAction[] = [
    {
      id: "exec-open",
      label: "Abrir detalle",
      icon: "👁",
      effect: "safe",
      quick: true,
      run: async (ctx) => {
        if (ctx.openDetail) ctx.openDetail(item.id);
        else ctx.navigate(serializeRoute({ tab: "history", exec: item.id, query: {} }));
      },
    },
    {
      id: "exec-copy-link",
      label: "Copiar link",
      icon: "🔗",
      effect: "safe",
      quick: true,
      run: async (ctx) => {
        // Se usa el `origin` que recibe la función, NO window: la página lo
        // inyecta, y así esto es testeable sin DOM (y no explota en SSR).
        const ok = await ctx.copyText(executionDeepLink(item.id, origin));
        ctx.onDone?.("exec-copy-link", ok);
      },
    },
    {
      id: "exec-copy-id",
      label: `Copiar id #${item.id}`,
      icon: "🆔",
      effect: "safe",
      quick: false,
      run: async (ctx) => {
        const ok = await ctx.copyText(String(item.id));
        ctx.onDone?.("exec-copy-id", ok);
      },
    },
  ];

  // No se ofrece lo que el backend va a rechazar: borrar o publicar una
  // ejecución en curso no es una opción, es una frustración.
  if (item.status === "running") {
    out.push({
      id: "exec-cancel",
      label: "Cancelar run…",
      icon: "⛔",
      effect: "confirm",
      quick: false,
      run: async (ctx) => {
        const ok = await ctx.askConfirm({
          title: "Cancelar run",
          message: `Cancelar la ejecución #${item.id} en curso.`,
          confirmLabel: "Cancelar run",
          tone: "danger",
        });
        if (!ok) return;
        await ctx.api.cancelExecution(item.id);
        ctx.onDone?.("exec-cancel", true);
      },
    });
    return out;
  }

  if (item.status === "completed") {
    out.push({
      id: "exec-publish",
      label: "Publicar a ADO…",
      icon: "📤",
      effect: "confirm",
      quick: false,
      run: async (ctx) => {
        const ok = await ctx.askConfirm({
          title: "Publicar a ADO",
          message: `Publicar el resultado de la ejecución #${item.id} como comentario en ADO.`,
          confirmLabel: "Publicar",
          tone: "default",
        });
        if (!ok) return;
        await ctx.api.publishExecution(item.id);
        ctx.onDone?.("exec-publish", true);
      },
    });
  }

  out.push({
    id: "exec-delete",
    label: "Borrar ejecución…",
    icon: "🗑",
    effect: "confirm",
    quick: false,
    run: async (ctx) => {
      const ok = await ctx.askConfirm({
        title: "Borrar ejecución",
        message: `Borrar la ejecución #${item.id}. Esta acción no se puede deshacer.`,
        confirmLabel: "Borrar",
        tone: "danger",
      });
      if (!ok) return;
      await ctx.api.deleteExecution(item.id);
      ctx.onDone?.("exec-delete", true);
    },
  });

  return out;
}

export function actionsForTicket(t: Ticket): EntityAction[] {
  const out: EntityAction[] = [];
  const ext = ticketExternalLink(t);

  if (ext) {
    out.push({
      id: "ticket-open-ado",
      label: "Abrir en ADO",
      icon: "↗",
      effect: "safe",
      quick: true,
      run: async (ctx) => ctx.openExternal(ext),
    });
    out.push({
      id: "ticket-copy-ado-link",
      label: "Copiar link ADO",
      icon: "🔗",
      effect: "safe",
      quick: true,
      run: async (ctx) => {
        const ok = await ctx.copyText(ext);
        ctx.onDone?.("ticket-copy-ado-link", ok);
      },
    });
  }

  out.push({
    id: "ticket-copy-ref",
    label: `Copiar ref ADO-${t.ado_id}`,
    icon: "🆔",
    effect: "safe",
    quick: false,
    run: async (ctx) => {
      const ok = await ctx.copyText(`ADO-${t.ado_id} — ${t.title}`);
      ctx.onDone?.("ticket-copy-ref", ok);
    },
  });

  return out;
}

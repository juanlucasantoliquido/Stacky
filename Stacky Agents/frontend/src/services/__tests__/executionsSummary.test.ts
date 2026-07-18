/**
 * Plan 156 F2 — Tests del poller central (latido único).
 * 100% puros + core de react-query en node (SIN DOM: no render(), no jsdom).
 */
import { describe, it, expect } from "vitest";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import type { AgentExecution, ExecutionsSummary } from "../../types";
import {
  executionsSummaryQueryKey,
  selectActiveRuns,
  selectRunningByTicket,
  summaryRefetchInterval,
} from "../executionsSummary";

function mkExec(id: number, ticket_id: number, status = "running"): AgentExecution {
  return { id, ticket_id, status, agent_type: "developer" } as unknown as AgentExecution;
}

function summaryOf(
  running: AgentExecution[],
  preparing: AgentExecution[],
  queued: AgentExecution[],
): ExecutionsSummary {
  return { scope: "project", running, preparing, queued };
}

describe("executionsSummary — poller central (plan 156 F2)", () => {
  it("test_backoff_visibilidad: ×4 en pestaña oculta, sin dato", () => {
    expect(summaryRefetchInterval("visible", undefined, 5000)).toBe(5000);
    expect(summaryRefetchInterval("hidden", undefined, 5000)).toBe(20000);
  });

  it("test_idle_backoff: ×2 sin runs, apilado con visibilidad", () => {
    const vacio = summaryOf([], [], []);
    expect(summaryRefetchInterval("visible", vacio, 5000)).toBe(10000);
    expect(summaryRefetchInterval("hidden", vacio, 5000)).toBe(40000);

    const conRuns = summaryOf([mkExec(1, 10)], [], []);
    expect(summaryRefetchInterval("visible", conRuns, 5000)).toBe(5000);

    // undefined (aún sin dato) → NO aplica idle backoff
    expect(summaryRefetchInterval("visible", undefined, 5000)).toBe(5000);
  });

  it("test_selectActiveRuns_dedup_orden: un id repetido → una aparición, orden id desc", () => {
    const running = [mkExec(2, 20)];
    const preparing = [mkExec(2, 20), mkExec(5, 50)]; // id 2 repetido
    const queued = [mkExec(1, 10)];
    const out = selectActiveRuns(summaryOf(running, preparing, queued));
    expect(out.map((e) => e.id)).toEqual([5, 2, 1]);
  });

  it("test_selectRunningByTicket: Set correcto; Map se queda con la 1ª (preparing→running→queued)", () => {
    const preparing = [mkExec(1, 5, "preparing")];
    const running = [mkExec(2, 5), mkExec(3, 7)]; // ticket 5 también en running
    const queued = [mkExec(4, 9, "queued")];
    const { ids, byTicket } = selectRunningByTicket(summaryOf(running, preparing, queued));
    expect([...ids].sort((a, b) => a - b)).toEqual([5, 7, 9]);
    // preparing gana el ticket 5 (execución id 1)
    expect(byTicket.get(5)?.id).toBe(1);
    expect(byTicket.get(7)?.id).toBe(3);
  });

  it("test_una_sola_request_por_key: N suscriptores ⇒ 1 request (react-query core, sin DOM)", async () => {
    let calls = 0;
    const queryFn = async (): Promise<ExecutionsSummary> => {
      calls += 1;
      return summaryOf([], [], []);
    };
    const qc = new QueryClient();
    const key = executionsSummaryQueryKey("project");

    const waitData = (obs: QueryObserver<ExecutionsSummary>) =>
      new Promise<void>((resolve) => {
        const unsub = obs.subscribe((r) => {
          if (r.data !== undefined && !r.isFetching) {
            unsub();
            resolve();
          }
        });
      });

    const o1 = new QueryObserver<ExecutionsSummary>(qc, { queryKey: key, queryFn });
    const o2 = new QueryObserver<ExecutionsSummary>(qc, { queryKey: key, queryFn });
    await Promise.all([waitData(o1), waitData(o2)]);

    expect(calls).toBe(1);
    qc.clear();
  });
});

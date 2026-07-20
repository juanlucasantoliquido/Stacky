import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { makeRecoveryHandler } from "./connectionRecovery";

describe("makeRecoveryHandler (Plan 192 F4)", () => {
  it("re-fetchea las queries ACTIVAS y marca stale las inactivas con UNA invalidacion", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
    });
    let activeCalls = 0;
    let inactiveCalls = 0;
    const observer = new QueryObserver(qc, {
      queryKey: ["activa"],
      queryFn: () => {
        activeCalls += 1;
        return Promise.resolve(activeCalls);
      },
    });
    const unsub = observer.subscribe(() => {});
    await vi.waitFor(() => expect(activeCalls).toBe(1));
    await qc.prefetchQuery({
      queryKey: ["inactiva"],
      queryFn: () => {
        inactiveCalls += 1;
        return Promise.resolve(inactiveCalls);
      },
    });
    expect(inactiveCalls).toBe(1);

    makeRecoveryHandler(qc)(); // el momento magico

    await vi.waitFor(() => expect(activeCalls).toBe(2)); // activa: re-fetch
    expect(inactiveCalls).toBe(1); // inactiva: NO re-fetch (thundering herd acotado)
    expect(qc.getQueryState(["inactiva"])?.isInvalidated).toBe(true); // pero queda stale
    unsub();
    qc.clear();
  });
});

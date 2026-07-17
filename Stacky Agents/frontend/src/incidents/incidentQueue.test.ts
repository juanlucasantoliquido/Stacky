import { describe, it, expect } from "vitest";
import { upsertQueueItem, queueSummary, mapStoreStatus, type QueueItem } from "./incidentQueue";

describe("upsertQueueItem", () => {
  it("reemplaza por id", () => {
    const items: QueueItem[] = [{ id: "a", title: "A", status: "analizando" }];
    const next: QueueItem = { id: "a", title: "A", status: "publicada", trackerId: "999" };
    const result = upsertQueueItem(items, next);
    expect(result).toHaveLength(1);
    expect(result[0].status).toBe("publicada");
    expect(result[0].trackerId).toBe("999");
  });

  it("agrega nuevo", () => {
    const items: QueueItem[] = [{ id: "a", title: "A", status: "analizando" }];
    const next: QueueItem = { id: "b", title: "B", status: "capturando" };
    const result = upsertQueueItem(items, next);
    expect(result).toHaveLength(2);
    expect(result.map((i) => i.id)).toEqual(["a", "b"]);
  });
});

describe("queueSummary", () => {
  it("cuenta publicadas y errores", () => {
    const items: QueueItem[] = [
      { id: "a", title: "A", status: "publicada" },
      { id: "b", title: "B", status: "error" },
      { id: "c", title: "C", status: "analizando" },
      { id: "d", title: "D", status: "publicada" },
    ];
    expect(queueSummary(items)).toEqual({ total: 4, publicadas: 2, errores: 1 });
  });
});

describe("mapStoreStatus", () => {
  it("mapa total incluye analizada y desconocidos", () => {
    expect(mapStoreStatus("capturada")).toBe("capturando");
    expect(mapStoreStatus("analizando")).toBe("analizando");
    expect(mapStoreStatus("analizada")).toBe("analizando");
    expect(mapStoreStatus("publicada")).toBe("publicada");
    expect(mapStoreStatus("error")).toBe("error");
    expect(mapStoreStatus("cualquier-cosa")).toBe("error");
    expect(mapStoreStatus(null)).toBe("error");
    expect(mapStoreStatus(undefined)).toBe("error");
  });
});

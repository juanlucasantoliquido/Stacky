// Plan 180 — F5: tests de la logica pura del panel de cobertura (vitest, sin RTL/jsdom).
import { describe, it, expect } from "vitest";

import { coverageSummary, groupCandidatesByTicket, severityOrder } from "./repoCoverageLogic";
import type { RepoCoverage, RepoCoverageItem } from "./repoCoverageTypes";

function mkItem(over: Partial<RepoCoverageItem>): RepoCoverageItem {
  return {
    object_type: "table",
    schema: "dbo",
    name: "T",
    action: "changed",
    severity: "info",
    candidates: [],
    ...over,
  };
}

describe("coverageSummary", () => {
  it("null input => null", () => {
    expect(coverageSummary(null)).toBeNull();
  });

  it("total_count 0 => null (panel no se renderiza)", () => {
    const cov: RepoCoverage = { items: [], covered_count: 0, total_count: 0 };
    expect(coverageSummary(cov)).toBeNull();
  });

  it("2 de 3 => {covered:2,total:3,pct:67} (Math.round)", () => {
    const cov: RepoCoverage = { items: [], covered_count: 2, total_count: 3 };
    expect(coverageSummary(cov)).toEqual({ covered: 2, total: 3, pct: 67 });
  });
});

describe("groupCandidatesByTicket", () => {
  it("ordena tickets numericos asc con null al final y dedup de paths", () => {
    const items: RepoCoverageItem[] = [
      mkItem({
        candidates: [
          { path: "b.sql", ticket: "600804", mtime: 2, matched_by: "TABLE" },
          { path: "b.sql", ticket: "600804", mtime: 2, matched_by: "TABLE" }, // dup
        ],
      }),
      mkItem({
        candidates: [
          { path: "a.sql", ticket: "600123", mtime: 1, matched_by: "SCHEMA.TABLE" },
          { path: "z.sql", ticket: null, mtime: 3, matched_by: "TABLE" },
        ],
      }),
    ];
    const groups = groupCandidatesByTicket(items);
    expect(groups.map((g) => g.ticket)).toEqual(["600123", "600804", null]);
    expect(groups[1].paths).toEqual(["b.sql"]); // dedup
  });
});

describe("severityOrder", () => {
  it("danger < warn < info, empate por schema.name asc", () => {
    const items: RepoCoverageItem[] = [
      mkItem({ severity: "info", schema: "dbo", name: "BINFO" }),
      mkItem({ severity: "danger", schema: "dbo", name: "ADANGER" }),
      mkItem({ severity: "warn", schema: "dbo", name: "CWARN" }),
      mkItem({ severity: "info", schema: "dbo", name: "AINFO" }),
    ];
    const ordered = severityOrder(items).map((i) => i.name);
    expect(ordered).toEqual(["ADANGER", "CWARN", "AINFO", "BINFO"]);
  });

  it("no muta el array de entrada", () => {
    const items: RepoCoverageItem[] = [
      mkItem({ severity: "info", name: "X" }),
      mkItem({ severity: "danger", name: "Y" }),
    ];
    const snapshot = items.map((i) => i.name);
    severityOrder(items);
    expect(items.map((i) => i.name)).toEqual(snapshot);
  });
});

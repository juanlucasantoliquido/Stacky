/**
 * Plan 129 F3 — Tests de las funciones puras de commandPaletteData.ts.
 *
 * Sin dependencias de React/testing-library: funciones puras.
 */
import { describe, it, expect, vi } from "vitest";
import { NAV_COMMANDS, mergeDeepResults, fuzzyScore } from "../commandPaletteData";
import type { RemoteGroup } from "../commandPaletteData";

describe("NAV_COMMANDS", () => {
  it("cubre los 13 tabs con paths unicos no vacios", () => {
    expect(NAV_COMMANDS.length).toBe(13);
    const paths = NAV_COMMANDS.map((c) => c.path);
    expect(paths.every((p) => typeof p === "string" && p.length > 0)).toBe(true);
    expect(new Set(paths).size).toBe(13);
  });
});

describe("mergeDeepResults", () => {
  const onNavigate = vi.fn();

  it("dedup: prefiere lo local (descarta hit remoto ya presente)", () => {
    const groups: RemoteGroup[] = [
      { kind: "ticket", hits: [{ kind: "ticket", id: "123", label: "T-1", hint: "", nav: "/tickets?ticket=123" }] },
    ];
    const localIds = new Set(["ticket-123"]);
    const out = mergeDeepResults(localIds, groups, onNavigate);
    expect(out).toEqual([]);
  });

  it("hit nuevo se incluye con el icono correcto", () => {
    const groups: RemoteGroup[] = [
      { kind: "server", hits: [{ kind: "server", id: "PF", label: "PF", hint: "10.10.1.5", nav: "/devops?server=PF" }] },
    ];
    const out = mergeDeepResults(new Set(), groups, onNavigate);
    expect(out).toHaveLength(1);
    expect(out[0].icon).toBe("🖥️");
    expect(out[0].id).toBe("server-PF");
    out[0].run();
    expect(onNavigate).toHaveBeenCalledWith("/devops?server=PF");
  });

  it("respeta el orden de los grupos de entrada", () => {
    const groups: RemoteGroup[] = [
      { kind: "execution", hits: [{ kind: "execution", id: "1", label: "Run #1", hint: "", nav: "/history?execution=1" }] },
      { kind: "doc", hits: [{ kind: "doc", id: "docs/x.md", label: "x.md", hint: "docs", nav: "/docs?path=docs%2Fx.md" }] },
    ];
    const out = mergeDeepResults(new Set(), groups, onNavigate);
    expect(out.map((c) => c.kind)).toEqual(["execution", "doc"]);
  });
});

describe("fuzzyScore (regresión — comportamiento intacto tras la mudanza)", () => {
  it("substring gana sobre coincidencia dispersa", () => {
    expect(fuzzyScore("plan", "plan.md")).toBeGreaterThan(0);
    expect(fuzzyScore("plan", "plan.md")).toBeGreaterThan(fuzzyScore("plan", "p_l_a_n.md"));
  });

  it("orden de caracteres importa (sin orden correcto no matchea)", () => {
    expect(fuzzyScore("abc", "xaxbxc")).toBeGreaterThan(0);
    expect(fuzzyScore("abc", "cba")).toBe(0);
  });

  it("sin match devuelve 0", () => {
    expect(fuzzyScore("zzz", "algo distinto")).toBe(0);
  });
});

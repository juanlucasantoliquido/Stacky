import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DocsPage.tsx";
describe("Plan 140 F6 — adopción Docs", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("usa SkeletonList y EmptyState docs", () => {
    expect(/<SkeletonList\b/.test(src())).toBe(true);
    expect(/variant="docs"/.test(src())).toBe(true);
  });
  it("usa formatRelativeTime en Indexado y ya no toLocaleTimeString", () => {
    expect(/formatRelativeTime\(/.test(src())).toBe(true);
    expect(/toLocaleTimeString/.test(src())).toBe(false);
  });
  it("NO reemplaza el texto de error del grafo (dominio 135)", () => {
    expect(/No se pudo cargar el grafo\./.test(src())).toBe(true);
  });
});

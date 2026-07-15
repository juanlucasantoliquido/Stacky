import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/TeamScreen.tsx";
describe("Plan 140 F7 — adopción Equipo", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("importa el EmptyState compartido", () => {
    expect(/import\s+SharedEmptyState\s+from\s+["']\.\.\/components\/EmptyState["']/.test(src())).toBe(true);
  });
  it("usa variantes agents y no_project", () => {
    expect(/variant="agents"/.test(src())).toBe(true);
    expect(/variant="no_project"/.test(src())).toBe(true);
  });
  it("ya no define EmptyState/NoProjectState locales", () => {
    expect(/function EmptyState\(/.test(src())).toBe(false);
    expect(/function NoProjectState\(/.test(src())).toBe(false);
  });
  it("skeleton migrado a la primitiva Skeleton", () => {
    expect(/<Skeleton\b/.test(src())).toBe(true);
    expect(/className=\{styles\.skeletonCard\}/.test(src())).toBe(false);
  });
});

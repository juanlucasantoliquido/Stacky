import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx";
describe("Plan 140 F5 — adopción Revisión", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("importa y usa SkeletonList", () => { expect(/import SkeletonList/.test(src())).toBe(true); expect(/<SkeletonList\b/.test(src())).toBe(true); });
  it("usa EmptyState compartido variante review", () => {
    expect(/from ["']\.\.\/components\/EmptyState["']/.test(src())).toBe(true);
    expect(/<EmptyState\b/.test(src())).toBe(true);
    expect(/variant="review"/.test(src())).toBe(true);
  });
  it("guarda el vacío contra error (C1, §10.7): usa isError en la condición", () => { expect(/isError/.test(src())).toBe(true); });
  it("usa StatusChip + runStatus", () => { expect(/<StatusChip\b/.test(src())).toBe(true); expect(/runStatusTone\(/.test(src())).toBe(true); });
  it("usa formatRelativeTime y ya no timeAgo local ni toLocale", () => {
    expect(/formatRelativeTime\(/.test(src())).toBe(true);
    expect(/function timeAgo/.test(src())).toBe(false);
    expect(/toLocale/.test(src())).toBe(false);
  });
});

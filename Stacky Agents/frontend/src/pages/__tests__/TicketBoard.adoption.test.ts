import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/TicketBoard.tsx";
describe("Plan 140 F8 — adopción acotada Tickets", () => {
  const src = () => readFileSync(SRC, "utf-8");
  it("carga de lista usa SkeletonList y ya no el texto plano", () => {
    expect(/<SkeletonList\b/.test(src())).toBe(true);
    expect(/Cargando jerarquía…/.test(src())).toBe(false);
  });
  it("vacío de lista usa EmptyState tickets", () => {
    expect(/variant="tickets"/.test(src())).toBe(true);
  });
  it("NO tocó zonas de running (siguen presentes)", () => {
    expect(/runningByTicket/.test(src())).toBe(true);
    expect(/runningPulse/.test(src())).toBe(true);
  });
});

// Plan 170 F6 — tests puros del modelo del flywheel (vitest, sin DOM — G5).
import { describe, it, expect } from "vitest";
import {
  scopeLabel,
  lessonStatusChip,
  formatDelta,
  validateManualLesson,
  sortCandidates,
  type LessonDto,
  type KnowledgeOverviewDto,
} from "./knowledgeModel";

function lesson(partial: Partial<LessonDto>): LessonDto {
  return {
    lesson_id: "l1",
    aspect_id: "knowledge_rag",
    text: "cuerpo",
    origin: "manual",
    created_at: "2026-01-01T00:00:00+00:00",
    active: true,
    title: "T",
    scope: { agent_types: [], projects: [], tags: [] },
    source: { kind: "manual", ref: null },
    eval_case_id: null,
    usage_count: 0,
    last_injected_at: null,
    ...partial,
  };
}

describe("scopeLabel", () => {
  it("global sin ejes", () => {
    expect(scopeLabel({ agent_types: [], projects: [], tags: [] })).toBe("Global");
  });
  it("con agentes une la lista", () => {
    expect(scopeLabel({ agent_types: ["developer", "qa"], projects: [], tags: [] })).toBe(
      "developer · qa",
    );
  });
});

describe("lessonStatusChip", () => {
  it("activa", () => {
    expect(lessonStatusChip(lesson({ active: true }))).toEqual({ tone: "success", label: "Activa" });
  });
  it("retirada", () => {
    expect(lessonStatusChip(lesson({ active: false }))).toEqual({ tone: "neutral", label: "Retirada" });
  });
});

describe("formatDelta", () => {
  it("null → guion", () => {
    expect(formatDelta(null)).toBe("—");
  });
  it("positivo con signo y 4 decimales", () => {
    expect(formatDelta(0.0312)).toBe("+0.0312");
  });
  it("negativo con signo", () => {
    expect(formatDelta(-0.02)).toBe("-0.0200");
  });
});

describe("validateManualLesson", () => {
  it("título vacío → error en title", () => {
    const r = validateManualLesson({ title: "  ", body: "cuerpo" });
    expect(r.ok).toBe(false);
    expect(r.errors.title).toBeTruthy();
  });
  it("body > 1200 → error en body", () => {
    const r = validateManualLesson({ title: "t", body: "x".repeat(1201) });
    expect(r.ok).toBe(false);
    expect(r.errors.body).toBeTruthy();
  });
  it("válido → ok sin errores", () => {
    const r = validateManualLesson({ title: "título", body: "cuerpo accionable" });
    expect(r.ok).toBe(true);
    expect(Object.keys(r.errors)).toHaveLength(0);
  });
});

describe("KnowledgeOverviewDto round-trip", () => {
  it("parsea sin any", () => {
    const ov: KnowledgeOverviewDto = {
      ok: true,
      lessons: { active: 1, retired: 0, cap: 200, over_cap: false },
      coverage: { agents_total: 14, agents_with_lessons: 1, by_agent_type: { developer: 1 } },
      flywheel: {
        incidents_published: 2,
        incidents_harvested: 1,
        eval_cases_from_incidents: 1,
        eval_cases_from_lessons: 0,
        optimizer_lessons_mejoro: 0,
        optimizer_lessons_promoted: 0,
      },
      usage: { injections_total: 3, never_injected: 0, top: [{ lesson_id: "l1", title: "T", usage_count: 3 }] },
      fitness_knowledge: { latest_score: 0.8, baseline_score: 0.6, delta: 0.2, runs: 2 },
      retire_suggestions: [],
    };
    expect(ov.coverage.by_agent_type.developer).toBe(1);
  });
});

describe("sortCandidates", () => {
  it("no cosechadas primero, luego created_at DESC", () => {
    const items = [
      { already_harvested: true, created_at: "2026-05-01", id: "a" },
      { already_harvested: false, created_at: "2026-01-01", id: "b" },
      { already_harvested: false, created_at: "2026-03-01", id: "c" },
    ];
    const out = sortCandidates(items).map((x) => x.id);
    expect(out).toEqual(["c", "b", "a"]);
  });
});

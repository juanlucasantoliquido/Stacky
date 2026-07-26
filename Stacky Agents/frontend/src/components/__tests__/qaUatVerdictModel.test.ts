/** Plan 214 F4 — Modelo puro del veredicto QA UAT. */
import { describe, expect, it } from "vitest";

import {
  candidateLabel,
  candidateTone,
  categoryLabel,
  readQaUatCandidate,
  readQaUatVerdict,
  verdictTone,
  weaknessNote,
} from "../qaUatVerdictModel";

describe("verdictTone", () => {
  it("mapea los 5 veredictos", () => {
    expect(verdictTone("PASS")).toBe("success");
    expect(verdictTone("FAIL")).toBe("danger");
    expect(verdictTone("BLOCKED")).toBe("warning");
    expect(verdictTone("MIXED")).toBe("warning");
    expect(verdictTone("SKIPPED")).toBe("neutral");
  });
  it("undefined es neutral", () => expect(verdictTone(undefined)).toBe("neutral"));
});

describe("categoryLabel", () => {
  it("traduce las 9 categorías reales", () => {
    expect(categoryLabel("NAV")).toBe("Navegación");
    expect(categoryLabel("DATA")).toBe("Datos");
    expect(categoryLabel("ENV")).toBe("Entorno");
    expect(categoryLabel("APP")).toBe("Aplicación");
    expect(categoryLabel("PIP")).toBe("Pipeline");
    expect(categoryLabel("GEN")).toBe("Generación");
    expect(categoryLabel("OBS")).toBe("Evidencia");
    expect(categoryLabel("SEC")).toBe("Seguridad");
    expect(categoryLabel("OPS")).toBe("Infraestructura");
  });
  it("una categoría desconocida se muestra CRUDA (no se oculta señal)", () => {
    expect(categoryLabel("XYZ")).toBe("XYZ");
  });
  it("vacía o undefined es guion", () => {
    expect(categoryLabel(undefined)).toBe("—");
    expect(categoryLabel("  ")).toBe("—");
  });
});

describe("weaknessNote", () => {
  it("un PASS con assertions débiles queda ANOTADO", () => {
    expect(weaknessNote(3, "PASS")).toContain("3");
  });
  it("PASS sin débiles no anota nada", () => expect(weaknessNote(0, "PASS")).toBeNull());
  it("solo aplica a PASS", () => expect(weaknessNote(3, "FAIL")).toBeNull());
  it("undefined no rompe", () => expect(weaknessNote(undefined, "PASS")).toBeNull());
});

describe("candidateLabel", () => {
  it("cubre los 5 estados", () => {
    expect(candidateLabel({ status: "pending" })).toBe("Validación E2E sugerida");
    expect(candidateLabel({ status: "blocked_by_build" })).toContain("build sin verificar");
    expect(candidateLabel({ status: "validated" })).toContain("PASS");
    expect(candidateLabel({ status: "failed" })).toContain("FALLÓ");
    expect(candidateLabel({ status: "blocked" })).toContain("BLOQUEADA");
  });
  it("estado desconocido o ausente es null", () => {
    expect(candidateLabel({ status: "raro" })).toBeNull();
    expect(candidateLabel(undefined)).toBeNull();
  });
});

describe("candidateTone", () => {
  it("no miente sobre el estado", () => {
    expect(candidateTone({ status: "validated" })).toBe("success");
    expect(candidateTone({ status: "failed" })).toBe("danger");
    expect(candidateTone({ status: "blocked_by_build" })).toBe("warning");
    expect(candidateTone({ status: "pending" })).toBe("info");
    expect(candidateTone(undefined)).toBe("neutral");
  });
});

describe("readQaUatVerdict", () => {
  it("null si no hay veredicto", () => {
    expect(readQaUatVerdict(undefined)).toBeNull();
    expect(readQaUatVerdict({})).toBeNull();
    expect(readQaUatVerdict({ verdict: "" })).toBeNull();
  });
  it("normaliza los campos presentes e ignora los rotos", () => {
    const out = readQaUatVerdict({
      verdict: "PASS",
      verdict_category: "NAV",
      nav_deviations: 0,
      weak_assertions_count: "dos",
      playbooks_used: ["a", "b"],
    });
    expect(out?.verdict).toBe("PASS");
    expect(out?.verdict_category).toBe("NAV");
    expect(out?.nav_deviations).toBe(0);
    expect(out?.weak_assertions_count).toBeUndefined();
    expect(out?.playbooks_used).toEqual(["a", "b"]);
  });
});

describe("readQaUatCandidate", () => {
  it("null si no aplica", () => {
    expect(readQaUatCandidate(undefined)).toBeNull();
    expect(readQaUatCandidate({ qa_uat_candidate: "texto" })).toBeNull();
  });
  it("devuelve el candidato", () => {
    const out = readQaUatCandidate({
      qa_uat_candidate: { status: "pending", ado_id: 70, mode: "dry-run" },
    });
    expect(out?.status).toBe("pending");
    expect(out?.ado_id).toBe(70);
  });
});

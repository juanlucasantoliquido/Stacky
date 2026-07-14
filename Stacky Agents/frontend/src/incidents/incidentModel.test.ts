import { describe, it, expect } from "vitest";
import {
  validateFiles,
  canAnalyze,
  summarizeRelatedEpic,
  pickResumableIncident,
  type IncidentStatusDTO,
  type IncidentDTO,
  type IncidentPreviewDTO,
} from "./incidentModel";

function status(overrides: Partial<IncidentStatusDTO> = {}): IncidentStatusDTO {
  return {
    enabled: true,
    max_files: 10,
    max_file_mb: 10,
    allowed_extensions: [".png", ".jpg", ".log", ".txt"],
    ...overrides,
  };
}

function incident(overrides: Partial<IncidentDTO> = {}): IncidentDTO {
  return {
    id: "inc_1",
    created_at: "2026-07-14T10:00:00+00:00",
    text: "texto",
    files: [],
    status: "capturada",
    execution_id: null,
    tracker_id: null,
    tracker_url: null,
    epic_id: null,
    doc_path: null,
    error: null,
    ...overrides,
  };
}

describe("validateFiles", () => {
  it("caso feliz: sin errores", () => {
    const result = validateFiles(
      [{ name: "captura.png", size: 1000 }, { name: "error.log", size: 2000 }],
      status()
    );
    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("extensión prohibida", () => {
    const result = validateFiles([{ name: "virus.exe", size: 10 }], status());
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("virus.exe"))).toBe(true);
  });

  it("más de max_files", () => {
    const files = Array.from({ length: 11 }, (_, i) => ({ name: `f${i}.log`, size: 10 }));
    const result = validateFiles(files, status());
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("Máximo"))).toBe(true);
  });

  it("archivo mayor a max_file_mb", () => {
    const result = validateFiles(
      [{ name: "big.log", size: 11 * 1024 * 1024 }],
      status({ max_file_mb: 10 })
    );
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("big.log"))).toBe(true);
  });
});

describe("canAnalyze", () => {
  it("solo texto → true", () => {
    expect(canAnalyze("algo de texto", [])).toBe(true);
  });

  it("solo archivos → true", () => {
    expect(canAnalyze("", [{ name: "a.png" }])).toBe(true);
  });

  it("nada → false", () => {
    expect(canAnalyze("   ", [])).toBe(false);
  });
});

describe("summarizeRelatedEpic", () => {
  it("con épica completa", () => {
    const preview: IncidentPreviewDTO = {
      ok: true,
      publishable: true,
      related_epic: { epic_id: 267, confidence: 85, reason: "afecta el alta de clientes" },
    };
    expect(summarizeRelatedEpic(preview)).toBe(
      "Épica 267 — confianza 85% — afecta el alta de clientes"
    );
  });

  it("sin épica", () => {
    const preview: IncidentPreviewDTO = {
      ok: true,
      publishable: true,
      related_epic: { epic_id: null, confidence: null, reason: null },
    };
    expect(summarizeRelatedEpic(preview)).toBe("Sin épica relacionada");
  });

  it("sin confianza", () => {
    const preview: IncidentPreviewDTO = {
      ok: true,
      publishable: true,
      related_epic: { epic_id: 5, confidence: null, reason: "motivo" },
    };
    expect(summarizeRelatedEpic(preview)).toBe("Épica 5 — motivo");
  });
});

describe("pickResumableIncident", () => {
  it("lista vacía → null", () => {
    expect(pickResumableIncident([])).toBeNull();
  });

  it("elige la más reciente en analizando/analizada", () => {
    const older = incident({ id: "inc_old", created_at: "2026-07-14T09:00:00+00:00", status: "analizando", execution_id: 1 });
    const newer = incident({ id: "inc_new", created_at: "2026-07-14T10:00:00+00:00", status: "analizada", execution_id: 2 });
    const result = pickResumableIncident([older, newer]);
    expect(result?.id).toBe("inc_new");
  });

  it("ignora publicada, con tracker_id, o sin execution_id", () => {
    const published = incident({ id: "inc_pub", status: "analizada", execution_id: 3, tracker_id: "999" });
    const noExec = incident({ id: "inc_noexec", status: "analizando", execution_id: null });
    const doneStatus = incident({ id: "inc_done", status: "publicada", execution_id: 4 });
    const result = pickResumableIncident([published, noExec, doneStatus]);
    expect(result).toBeNull();
  });
});

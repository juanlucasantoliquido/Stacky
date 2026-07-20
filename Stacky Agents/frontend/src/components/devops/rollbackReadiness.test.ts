import { describe, it, expect } from "vitest";
import {
  readinessBadge,
  stepRows,
  commandsClipboardText,
  REASON_LABELS,
  type Readiness,
} from "./rollbackReadiness";

const base: Readiness = {
  ready: true,
  to_version: "v2",
  candidates: ["v2", "v1"],
  current_version: "v3",
  protected: false,
  locked: false,
  reasons: [],
};

describe("readinessBadge", () => {
  it("undefined → tone none, sin texto", () => {
    const b = readinessBadge(undefined);
    expect(b.tone).toBe("none");
    expect(b.text).toBe("");
  });

  it("ready → tone ok con la versión destino", () => {
    const b = readinessBadge(base);
    expect(b.tone).toBe("ok");
    expect(b.text).toContain("v2");
    expect(b.title).toBe(""); // no protegido → sin aviso
  });

  it("ready + protected → title avisa confirmación extra", () => {
    const b = readinessBadge({ ...base, protected: true });
    expect(b.tone).toBe("ok");
    expect(b.title.toLowerCase()).toContain("protegido");
  });

  it("no-ready → tone off, title junta los motivos traducidos", () => {
    const b = readinessBadge({
      ...base,
      ready: false,
      to_version: null,
      candidates: [],
      reasons: ["sin_versiones_retenidas", "run_en_curso"],
    });
    expect(b.tone).toBe("off");
    expect(b.title).toContain(REASON_LABELS["sin_versiones_retenidas"]);
    expect(b.title).toContain(REASON_LABELS["run_en_curso"]);
  });

  it("no-ready con reason desconocido → lo deja crudo", () => {
    const b = readinessBadge({
      ...base,
      ready: false,
      reasons: ["motivo_marciano"],
    });
    expect(b.tone).toBe("off");
    expect(b.title).toContain("motivo_marciano");
  });
});

describe("stepRows", () => {
  it("mapea tags según read_only / housekeeping", () => {
    const rows = stepRows({
      steps: [
        { name: "preflight", command: "x", read_only: true },
        { name: "switch", command: "y" },
        { name: "cleanup", command: "z", housekeeping: true },
      ],
    });
    expect(rows.length).toBe(3);
    expect(rows[0].tags).toContain("solo lectura");
    expect(rows[1].tags).toEqual([]);
    expect(rows[2].tags).toContain("housekeeping");
    expect(rows[1].command).toBe("y");
  });

  it("null → []", () => {
    expect(stepRows(null)).toEqual([]);
  });
});

describe("commandsClipboardText", () => {
  it("2 steps → 2 líneas unidas por \\n", () => {
    const txt = commandsClipboardText({
      steps: [{ command: "cmd uno" }, { command: "cmd dos" }],
    });
    expect(txt).toBe("cmd uno\ncmd dos");
  });

  it("null → ''", () => {
    expect(commandsClipboardText(null)).toBe("");
  });
});

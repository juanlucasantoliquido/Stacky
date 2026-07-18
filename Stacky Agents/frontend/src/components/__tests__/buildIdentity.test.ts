// Plan 163 F2 — tests puros del chip de identidad de build (sin render()).
import { describe, it, expect } from "vitest";
import {
  versionChipLabel,
  shortHash,
  buildTooltip,
  driftMessage,
  type BuildIdentity,
} from "../buildIdentity";

describe("buildIdentity", () => {
  it("test_chip_label_con_hash", () => {
    expect(
      versionChipLabel({ version: "1.0.76", sourceCommit: "a1b2c3d4e", builtAt: null, drift: false })
    ).toBe("v1.0.76 · a1b2c3d");
  });

  it("test_chip_label_dev", () => {
    expect(
      versionChipLabel({ version: null, sourceCommit: null, builtAt: null, drift: false })
    ).toBe("dev@local");
  });

  it("test_tooltip_incluye_built_at", () => {
    const t = buildTooltip({
      version: "1.0.76",
      sourceCommit: "a1b2c3d",
      builtAt: "2026-07-14 18:00",
      drift: false,
    });
    expect(t).toContain("build 2026-07-14 18:00");
    expect(t).toContain("commit a1b2c3d");
  });

  it("test_short_hash", () => {
    expect(shortHash("a1b2c3d4e5f6")).toBe("a1b2c3d");
    expect(shortHash(null)).toBe("");
  });

  it("test_drift_message", () => {
    const m = driftMessage({
      version: "1.0.76",
      sourceCommit: "a1b2c3d",
      builtAt: null,
      drift: true,
    } as BuildIdentity);
    expect(m).toContain("a1b2c3d");
    expect(m).toContain("Reiniciá el backend");
  });
});

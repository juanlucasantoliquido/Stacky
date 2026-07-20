import { readFileSync } from "fs";
import { join } from "path";
import { describe, it, expect } from "vitest";

const FILES = [
  "src/components/IncidentResolverModal.tsx",
  "src/components/EpicFromBriefModal.tsx",
  "src/components/ModelDecisionChip.tsx",
];

describe("Plan 159 — sin listas de modelos hardcodeadas fuera del catálogo", () => {
  for (const rel of FILES) {
    const src = readFileSync(join(process.cwd(), rel), "utf-8");
    it(`${rel} no declara CLAUDE_MODELS/CLAUDE_EFFORTS/ALT_MODELS local`, () => {
      expect(src).not.toMatch(/const\s+CLAUDE_MODELS\s*[:=]/);
      expect(src).not.toMatch(/const\s+CLAUDE_EFFORTS\s*[:=]/);
      expect(src).not.toMatch(/const\s+ALT_MODELS\s*[:=]/);
    });
    it(`${rel} no contiene el literal stale claude-opus-4-7`, () => {
      expect(src).not.toContain("claude-opus-4-7");
    });
  }
});

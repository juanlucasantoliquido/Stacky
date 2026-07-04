/**
 * Tests de presetsModel.ts - Plan 88 F4
 * TDD: lógica pura de edición de presets de publicación (sin React)
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import {
  emptyPreset,
  upsertPreset,
  removePreset,
  validatePresetLocal,
  mergeKeysIntoProfile,
  resolvePreview,
  presetsEqual,
  draftNameForPreset,
  type PublicationPreset,
} from "./presetsModel";

const fixture = JSON.parse(
  readFileSync(
    new URL("../../../backend/tests/fixtures/plan88_resolution_cases.json", import.meta.url),
    "utf-8",
  ),
);

describe("presetsModel", () => {
  it("upsert_replaces_by_name_immutable", () => {
    const list: PublicationPreset[] = [{ name: "a", mode: "todo", groups: [] }];
    const updated: PublicationPreset = { name: "a", mode: "selection", groups: ["batch"], process_names: ["X"] };
    const next = upsertPreset(list, updated);
    expect(next).toEqual([updated]);
    expect(list).toEqual([{ name: "a", mode: "todo", groups: [] }]); // input no mutado

    const withNew = upsertPreset(list, { name: "b", mode: "todo", groups: [] });
    expect(withNew.length).toBe(2);
  });

  it("remove_absent_noop", () => {
    const list: PublicationPreset[] = [{ name: "a", mode: "todo", groups: [] }];
    const next = removePreset(list, "no-existe");
    expect(next).toEqual(list);
    expect(next).not.toBe(list);
  });

  it("validate_selection_without_names_fails", () => {
    const errors = validatePresetLocal({ name: "a", mode: "selection", groups: [] });
    expect(errors.length).toBeGreaterThan(0);
  });

  it("validate_todo_ok", () => {
    const errors = validatePresetLocal({ name: "a", mode: "todo", groups: [] });
    expect(errors).toEqual([]);
  });

  it("resolvePreview_shared_fixture_parity", () => {
    for (const c of fixture.cases) {
      const result = resolvePreview(c.preset, fixture.catalog);
      expect(result.resolved).toEqual(c.resolved);
      expect(result.unknown).toEqual(c.unknown);
    }
  });

  it("mergeKeys_preserves_foreign_keys", () => {
    const profile = { process_catalog: [{ kind: "entry" }], otra_key: 1 };
    const preset: PublicationPreset = { name: "a", mode: "todo", groups: [] };
    const merged: any = mergeKeysIntoProfile(profile, { devops_publication_presets: [preset] });
    expect(merged.process_catalog).toEqual(profile.process_catalog);
    expect(merged.otra_key).toBe(1);
    expect(merged.devops_publication_presets).toEqual([preset]);
    expect(profile).toEqual({ process_catalog: [{ kind: "entry" }], otra_key: 1 }); // no mutó
  });

  it("mergeKeys_null_profile", () => {
    const merged = mergeKeysIntoProfile(null, { devops_publication_presets: [] });
    expect(merged).toEqual({ devops_publication_presets: [] });
  });

  it("presetsEqual_detects_changes", () => {
    const list: PublicationPreset[] = [{ name: "a", mode: "todo", groups: [] }];
    expect(presetsEqual(list, list)).toBe(true);
    const changed = upsertPreset(list, { name: "a", mode: "todo", groups: ["batch"] });
    expect(presetsEqual(list, changed)).toBe(false);
  });

  it("draftName_no_collision", () => {
    expect(draftNameForPreset([], "quincena")).toBe("preset-quincena");
  });

  it("draftName_unique_suffix", () => {
    expect(
      draftNameForPreset(["preset-quincena", "preset-quincena-2"], "quincena"),
    ).toBe("preset-quincena-3");
    const longName = "x".repeat(120);
    const result = draftNameForPreset([], longName);
    expect(result.length).toBeLessThanOrEqual(120);
  });
});

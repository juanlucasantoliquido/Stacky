/**
 * Tests de environmentModel.ts - Plan 89 F5
 * TDD: lógica pura del wizard de inicialización de ambientes (sin React).
 */
import { describe, it, expect } from "vitest";
import {
  emptyEnvironmentSettings,
  validateSettingsLocal,
  summarizePlan,
  selectablePaths,
  allExistsOk,
  type PlanEntry,
} from "./environmentModel";

describe("environmentModel", () => {
  it("empty_settings_pacifico_defaults", () => {
    const s = emptyEnvironmentSettings();
    expect(s.folder_layout.entry).toContain("IN_");
    expect(s.folder_layout.processing).toContain("productivas");
    expect(s.folder_layout.output).toContain("salida");
    // editable: no es un objeto congelado
    s.folder_layout.entry.push("otra");
    expect(s.folder_layout.entry).toEqual(["IN_", "otra"]);
  });

  it("validate_root_relative_fails", () => {
    const errors = validateSettingsLocal({
      environment_root: "relativo/x",
      folder_layout: { entry: [], processing: [], output: [], default: [] },
      per_process_subfolder: false,
    });
    expect(errors.length).toBeGreaterThan(0);
  });

  it("validate_segment_traversal_fails", () => {
    const errors = validateSettingsLocal({
      environment_root: "C:\\ambientes\\pacifico",
      folder_layout: { entry: ["../fuga"], processing: [], output: [], default: [] },
      per_process_subfolder: false,
    });
    expect(errors.length).toBeGreaterThan(0);
  });

  it("validate_segment_windows_char_fails", () => {
    const e1 = validateSettingsLocal({
      environment_root: "C:\\ambientes\\pacifico",
      folder_layout: { entry: ["IN|X"], processing: [], output: [], default: [] },
      per_process_subfolder: false,
    });
    expect(e1.length).toBeGreaterThan(0);

    const e2 = validateSettingsLocal({
      environment_root: "C:\\ambientes\\pacifico",
      folder_layout: { entry: ["CON"], processing: [], output: [], default: [] },
      per_process_subfolder: false,
    });
    expect(e2.length).toBeGreaterThan(0);
  });

  it("summarize_counts", () => {
    const entries: PlanEntry[] = [
      { path: "a", status: "to_create", reason: null },
      { path: "b", status: "exists_ok", reason: null },
      { path: "c", status: "conflict", reason: null },
      { path: "d", status: "unsafe", reason: "fuera_de_root" },
      { path: "e", status: "to_create", reason: null },
    ];
    const summary = summarizePlan(entries);
    expect(summary).toEqual({ to_create: 2, exists_ok: 1, conflict: 1, unsafe: 1 });
  });

  it("selectable_only_to_create", () => {
    const entries: PlanEntry[] = [
      { path: "a", status: "to_create", reason: null },
      { path: "b", status: "exists_ok", reason: null },
      { path: "c", status: "conflict", reason: null },
    ];
    expect(selectablePaths(entries)).toEqual(["a"]);
  });

  it("all_exists_ok_badge", () => {
    const allOk: PlanEntry[] = [
      { path: "a", status: "exists_ok", reason: null },
      { path: "b", status: "exists_ok", reason: null },
    ];
    expect(allExistsOk(allOk)).toBe(true);

    const withPending: PlanEntry[] = [
      { path: "a", status: "exists_ok", reason: null },
      { path: "b", status: "to_create", reason: null },
    ];
    expect(allExistsOk(withPending)).toBe(false);

    const withConflict: PlanEntry[] = [
      { path: "a", status: "exists_ok", reason: null },
      { path: "b", status: "conflict", reason: null },
    ];
    expect(allExistsOk(withConflict)).toBe(false);

    expect(allExistsOk([])).toBe(false);
  });
});

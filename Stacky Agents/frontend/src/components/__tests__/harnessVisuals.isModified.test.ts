/**
 * Plan 82 F3 — Tests de la función pura isModifiedFromDefault (harnessVisuals.ts).
 *
 * Sin dependencias de React/testing-library: función pura sobre un objeto plano.
 */
import { describe, it, expect } from "vitest";
import { isModifiedFromDefault } from "../harnessVisuals";

describe("isModifiedFromDefault", () => {
  // test_bool_default_off_value_on_is_modified
  it("bool: default OFF y value ON es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: false, value: true, type: "bool" }),
    ).toBe(true);
  });

  it("bool: default OFF y value OFF no es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: false, value: false, type: "bool" }),
    ).toBe(false);
  });

  // test_default_unknown_never_modified
  it("default_known=false nunca es modificada, sin importar el valor", () => {
    expect(
      isModifiedFromDefault({ default_known: false, default: false, value: true, type: "bool" }),
    ).toBe(false);
    expect(
      isModifiedFromDefault({ default_known: false, default: 5, value: 999, type: "int" }),
    ).toBe(false);
  });

  // test_csv_empty_equals_null_default_not_modified
  it("csv: value vacío y default null/undefined no es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: null, value: "", type: "csv" }),
    ).toBe(false);
    expect(
      isModifiedFromDefault({ default_known: true, default: undefined, value: "", type: "csv" }),
    ).toBe(false);
  });

  it("csv: value no vacío contra default null SÍ es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: null, value: "proj-a", type: "csv" }),
    ).toBe(true);
  });

  // test_int_string_vs_number_same_value_not_modified
  it("int: default numérico y value string del mismo número no es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: 3, value: "3", type: "int" }),
    ).toBe(false);
  });

  it("int: default numérico y value string distinto SÍ es modificada", () => {
    expect(
      isModifiedFromDefault({ default_known: true, default: 3, value: "5", type: "int" }),
    ).toBe(true);
  });
});

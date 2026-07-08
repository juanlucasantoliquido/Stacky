/**
 * Tests de variablesModel.ts - Plan 94 F4
 * TDD: lógica pura de variables CI (sin React), paridad py↔ts por fixture compartido.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import {
  looksSecret,
  validateVariableKey,
  canBeMasked,
  splitSpecVariables,
} from "./variablesModel";
import { removeSpecVariable, emptySpec } from "./specBuilder";

const fixture = JSON.parse(
  readFileSync(
    new URL("../../../backend/tests/fixtures/plan94_secret_hints.json", import.meta.url),
    "utf-8",
  ),
);

describe("variablesModel", () => {
  it("looksSecret_shared_fixture_parity", () => {
    for (const key of fixture.secret as string[]) {
      expect(looksSecret(key), `esperaba secreto: ${key}`).toBe(true);
    }
    for (const key of fixture.not_secret as string[]) {
      expect(looksSecret(key), `esperaba NO secreto: ${key}`).toBe(false);
    }
  });

  it("validate_key_mirror", () => {
    expect(validateVariableKey("DEPLOY_PATH")).toBeNull();
    expect(validateVariableKey("_x")).toBeNull();
    expect(validateVariableKey("")).not.toBeNull();
    expect(validateVariableKey("9X")).not.toBeNull();
    expect(validateVariableKey("con espacios")).not.toBeNull();
    expect(validateVariableKey("a-b")).not.toBeNull();
    expect(validateVariableKey("x".repeat(256))).not.toBeNull();
  });

  it("splitSpecVariables_detects", () => {
    const spec = { variables: { DB_PASSWORD: "x", DEPLOY_PATH: "/app" } };
    const { secretLooking, plain } = splitSpecVariables(spec);
    expect(secretLooking).toEqual(["DB_PASSWORD"]);
    expect(plain).toEqual(["DEPLOY_PATH"]);
  });

  it("removeSpecVariable_immutable", () => {
    const spec = { ...emptySpec(), variables: { DB_PASSWORD: "x", DEPLOY_PATH: "/app" } };
    const next = removeSpecVariable(spec, "DB_PASSWORD");
    expect(next.variables).toEqual({ DEPLOY_PATH: "/app" });
    // Inmutable: el original no se toca
    expect(spec.variables).toEqual({ DB_PASSWORD: "x", DEPLOY_PATH: "/app" });
    // NOOP si la key no existe
    expect(removeSpecVariable(spec, "NO_EXISTE")).toBe(spec);
  });

  it("canBeMasked_rules", () => {
    expect(canBeMasked("short")).toBe(false); // < 8 chars
    expect(canBeMasked("multi\nline12")).toBe(false); // con \n
    expect(canBeMasked("con espacio1")).toBe(false); // charset inválido (espacio)
    expect(canBeMasked("Abcd1234~")).toBe(true);
  });
});

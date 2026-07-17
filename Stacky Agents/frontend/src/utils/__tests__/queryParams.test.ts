/**
 * Plan 129 F4 — Tests de parseQueryParam (función pura, sin jsdom).
 *
 * El entorno de vitest de este repo NO tiene jsdom por defecto (confirmado:
 * `window is not defined` al testear readQueryParam directamente), tal como
 * anticipa el plan v2 (§F4): se testea SOLO la función pura parseQueryParam,
 * dejando readQueryParam como wrapper de 1 línea sin test directo.
 */
import { describe, it, expect } from "vitest";
import { parseQueryParam } from "../queryParams";

describe("parseQueryParam (puro)", () => {
  it("param presente devuelve su valor", () => {
    expect(parseQueryParam("?execution=42", "execution")).toBe("42");
  });

  it("param ausente devuelve null", () => {
    expect(parseQueryParam("?x=1", "execution")).toBeNull();
  });

  it("param urlencoded se decodifica", () => {
    expect(parseQueryParam("?path=docs%2Fplan.md", "path")).toBe("docs/plan.md");
  });
});

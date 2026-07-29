// Plan 266 F5 — Lógica pura del diagnóstico del boundary (sin RTL/jsdom).
import { describe, it, expect } from "vitest";
import {
  firstComponentFromStack,
  buildActivityBody,
  buildDiagnosticText,
  MAX_MESSAGE_CHARS,
  MAX_STACK_CHARS,
} from "../errorBoundaryDiagnostics";

describe("Plan 266 F5 — firstComponentFromStack", () => {
  it("extrae el componente de una línea `in X (at ...)`", () => {
    expect(firstComponentFromStack("\n    in RunsTimeline (at DbComparePage.tsx:81)")).toBe(
      "RunsTimeline",
    );
  });

  it("extrae el componente de una línea `at X`", () => {
    expect(firstComponentFromStack("    at SummaryHero\n    at DbComparePage")).toBe(
      "SummaryHero",
    );
  });

  it("basura sin formato -> null", () => {
    expect(firstComponentFromStack("basura sin formato")).toBeNull();
  });

  it('"" -> null', () => {
    expect(firstComponentFromStack("")).toBeNull();
  });

  it("undefined -> null", () => {
    expect(firstComponentFromStack(undefined)).toBeNull();
  });
});

describe("Plan 266 F5 — buildActivityBody", () => {
  it("con componente: '<surface> · <componentName>: <message>'", () => {
    expect(buildActivityBody("Comparador de BD", "RunsTimeline", "boom")).toBe(
      "Comparador de BD · RunsTimeline: boom",
    );
  });

  it("sin componente: '<surface>: <message>'", () => {
    expect(buildActivityBody("Comparador de BD", null, "boom")).toBe("Comparador de BD: boom");
  });

  it("mensaje vacío -> 'error desconocido'", () => {
    expect(buildActivityBody("Comparador de BD", null, "")).toBe(
      "Comparador de BD: error desconocido",
    );
  });
});

describe("Plan 266 F5 — buildDiagnosticText", () => {
  it("con stack: agrega el bloque Stack: al final", () => {
    const text = buildDiagnosticText({
      surface: "Comparador de BD",
      message: "boom",
      componentName: "RunsTimeline",
      stack: "at RunsTimeline\nat DbComparePage",
      iso: "2026-07-27T10:00:00Z",
    });
    expect(text).toBe(
      "Stacky — error de render\n" +
        "Superficie: Comparador de BD\n" +
        "Componente: RunsTimeline\n" +
        "Mensaje: boom\n" +
        "Cuándo: 2026-07-27T10:00:00Z\n" +
        "\n" +
        "Stack:\n" +
        "at RunsTimeline\nat DbComparePage",
    );
  });

  it("sin stack: NO agrega el bloque Stack:", () => {
    const text = buildDiagnosticText({
      surface: "Comparador de BD",
      message: "boom",
      componentName: "RunsTimeline",
      stack: null,
      iso: "2026-07-27T10:00:00Z",
    });
    expect(text).not.toContain("Stack:");
  });

  it("componentName null -> 'Componente: desconocido'", () => {
    const text = buildDiagnosticText({
      surface: "Comparador de BD",
      message: "boom",
      componentName: null,
      stack: null,
      iso: "2026-07-27T10:00:00Z",
    });
    expect(text).toContain("Componente: desconocido");
  });

  it("es determinista: mismos argumentos, mismo string", () => {
    const args = {
      surface: "s",
      message: "m",
      componentName: "c",
      stack: "k",
      iso: "2026-07-27T10:00:00Z",
    };
    expect(buildDiagnosticText(args)).toBe(buildDiagnosticText(args));
  });
});

// --------------------------------------------------------------------------
// C30 — cotas de datos personales (NO cosmético). El Comparador trabaja contra
// bases de datos reales: message/stack no pueden acumularse sin límite.
// --------------------------------------------------------------------------

describe("Plan 266 F5 — cotas de datos personales (C30)", () => {
  it("buildDiagnosticText trunca un stack gigante", () => {
    const stack = "x".repeat(20000);
    const text = buildDiagnosticText({
      surface: "s",
      message: "m",
      componentName: null,
      stack,
      iso: "2026-07-27T10:00:00Z",
    });
    expect(text.length).toBeLessThan(MAX_STACK_CHARS + 400);
    expect(text).toContain("…[truncado]");
  });

  it("buildDiagnosticText trunca un mensaje gigante", () => {
    const message = "y".repeat(5000);
    const text = buildDiagnosticText({
      surface: "s",
      message,
      componentName: null,
      stack: null,
      iso: "2026-07-27T10:00:00Z",
    });
    const mensajeLinea = text.split("\n").find((l) => l.startsWith("Mensaje:"))!;
    // Margen generoso para el prefijo "Mensaje: " + el sufijo de truncado (no
    // se ata al conteo exacto de caracteres del sufijo, solo a que NO crezca
    // sin límite).
    expect(mensajeLinea.length).toBeLessThan(MAX_MESSAGE_CHARS + 30);
    expect(mensajeLinea).toContain("…[truncado]");
  });

  it("buildActivityBody trunca el mensaje", () => {
    const message = "z".repeat(5000);
    const body = buildActivityBody("s", null, message);
    expect(body.length).toBeLessThan(MAX_MESSAGE_CHARS + 100);
    expect(body).toContain("…[truncado]");
  });

  it("buildDiagnosticText no filtra nada más que los 5 campos (anti-filtración)", () => {
    const input = { surface: "s", message: "m", componentName: "c", stack: "k", iso: "i" };
    const text = buildDiagnosticText(input);
    // Quitamos la plantilla fija y los 5 valores: lo que sobra no puede tener
    // ninguna subcadena de más de 3 caracteres que no sea de la plantilla.
    let resto = text;
    for (const fixed of [
      "Stacky — error de render",
      "Superficie: ",
      "Componente: ",
      "Mensaje: ",
      "Cuándo: ",
      "\n\nStack:\n",
      "\n",
    ]) {
      resto = resto.split(fixed).join("");
    }
    for (const value of Object.values(input)) {
      resto = resto.split(value).join("");
    }
    expect(resto.trim()).toBe("");
  });
});

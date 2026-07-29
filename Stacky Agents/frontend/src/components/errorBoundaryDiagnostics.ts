// Plan 266 F5 — Lógica pura del diagnóstico del boundary (testeable sin RTL/jsdom).

/** Cotas de datos personales (C30). El Comparador trabaja contra bases de datos
 * REALES: un `message` de error puede arrastrar un valor de fila, y el `body`
 * que publica buildActivityBody queda en localStorage para siempre. */
export const MAX_MESSAGE_CHARS = 500;
export const MAX_STACK_CHARS = 4000;

const TRUNCATE_SUFFIX = " …[truncado]";

function truncar(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + TRUNCATE_SUFFIX;
}

/** Primer componente del componentStack de React. `null` si no se puede extraer. */
export function firstComponentFromStack(stack: string | null | undefined): string | null {
  if (!stack) return null;
  const match = /^\s*(?:at|in)\s+([A-Za-z0-9_$.]+)/m.exec(stack);
  return match ? match[1] : null;
}

/** Línea corta para el Centro de Actividad. Trunca `message` a MAX_MESSAGE_CHARS. */
export function buildActivityBody(
  surface: string,
  componentName: string | null,
  message: string,
): string {
  const msg = truncar(message || "error desconocido", MAX_MESSAGE_CHARS);
  return componentName ? `${surface} · ${componentName}: ${msg}` : `${surface}: ${msg}`;
}

/** Texto determinista para el portapapeles. Sin timestamps implícitos: el reloj entra por parámetro. */
export function buildDiagnosticText(input: {
  surface: string;
  message: string;
  componentName: string | null;
  stack: string | null;
  iso: string;
}): string {
  const { surface, message, componentName, stack, iso } = input;
  const lines = [
    "Stacky — error de render",
    `Superficie: ${surface}`,
    `Componente: ${componentName ?? "desconocido"}`,
    `Mensaje: ${truncar(message, MAX_MESSAGE_CHARS)}`,
    `Cuándo: ${iso}`,
  ];
  let out = lines.join("\n");
  if (stack) {
    out += "\n\nStack:\n" + truncar(stack, MAX_STACK_CHARS);
  }
  return out;
}

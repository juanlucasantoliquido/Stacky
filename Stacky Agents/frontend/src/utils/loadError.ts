/**
 * Convierte cualquier error atrapado en un mensaje corto y legible para la UI.
 * Los errores de `api/client.ts` (request, :76-78) tienen message =
 * "<status> <statusText>: <body crudo>" — acá se colapsa whitespace y se
 * trunca para que un body HTML/JSON largo no rompa el layout.
 */
export function formatLoadErrorMessage(error: unknown, maxLen = 140): string {
  let msg: string;
  if (error instanceof Error) msg = error.message;
  else if (typeof error === "string") msg = error;
  else msg = "";
  msg = msg.replace(/\s+/g, " ").trim();
  if (!msg) return "error desconocido";
  if (msg.length > maxLen) return msg.slice(0, maxLen - 1) + "…";
  return msg;
}

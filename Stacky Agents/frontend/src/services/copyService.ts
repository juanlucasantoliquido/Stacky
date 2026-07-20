/**
 * copyService.ts — Plan 194 F1. Punto ÚNICO de escritura al portapapeles.
 *
 * - copyText(text): camino moderno (navigator.clipboard.writeText) con fallback
 *   textarea+execCommand para contextos NO-seguros (http://IP:puerto en LAN, el
 *   deploy típico de Stacky, donde navigator.clipboard es undefined — §4.9). El
 *   fallback PRESERVA foco y selección del operador (a11y).
 * - copyRichText(html, plain): doble formato text/html + text/plain vía
 *   ClipboardItem (§4.11), con degradación honesta a copyText(plain).
 * - resolveCopyExportEnabled: wrapper de flagGate (197 §6.1) para la flag 194.
 *
 * NUNCA muestra toasts ni toca el DOM visible: devuelve CopyResult y el caller
 * decide el feedback (§4.4).
 */
import { flagEnabledFrom } from "./flagGate";

export type CopySuccessMethod = "clipboard" | "execCommand" | "richClipboard";

export type CopyResult =
  | { ok: true; method: CopySuccessMethod }
  | { ok: false; reason: "empty" | "denied" | "unavailable" };

export const COPY_TOAST_SUCCESS = "Copiado al portapapeles.";
export const COPY_TOAST_ERROR = "No se pudo copiar al portapapeles.";

/** Key de la flag 194 (compartida con config.py / harness_flags.py). */
export const COPY_EXPORT_FLAG_KEY = "STACKY_COPY_EXPORT_ENABLED";

export async function copyText(text: string): Promise<CopyResult> {
  if (text === "") return { ok: false, reason: "empty" };
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  const hasAsync = typeof nav?.clipboard?.writeText === "function";
  if (hasAsync) {
    try {
      await nav!.clipboard.writeText(text);
      return { ok: true, method: "clipboard" };
    } catch {
      /* permiso denegado o contexto no-seguro: cae al fallback */
    }
  }
  const doc = typeof document !== "undefined" ? document : undefined;
  if (!doc || typeof doc.execCommand !== "function") {
    return { ok: false, reason: hasAsync ? "denied" : "unavailable" };
  }
  try {
    // §4.9 — foto del foco y la selección ANTES de tocar el DOM (guards
    // defensivos: los stubs planos de los tests no definen activeElement/
    // getSelection y NO deben romper).
    const prevActive = (doc.activeElement ?? null) as { focus?: () => void } | null;
    const sel = typeof doc.getSelection === "function" ? doc.getSelection() : null;
    const prevRanges: Range[] = [];
    if (sel && typeof sel.rangeCount === "number" && typeof sel.getRangeAt === "function") {
      for (let i = 0; i < sel.rangeCount; i++) prevRanges.push(sel.getRangeAt(i));
    }

    const ta = doc.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.setAttribute("aria-hidden", "true");
    ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0;"; // .ts imperativo, no JSX (G7)
    doc.body.appendChild(ta);
    ta.select();
    const ok = doc.execCommand("copy");
    doc.body.removeChild(ta);

    // §4.9 — restaurar selección y foco (mismo orden: primero ranges, después foco).
    if (sel && typeof sel.removeAllRanges === "function" && prevRanges.length > 0) {
      sel.removeAllRanges();
      for (const r of prevRanges) sel.addRange(r);
    }
    if (prevActive && typeof prevActive.focus === "function") prevActive.focus();

    return ok ? { ok: true, method: "execCommand" } : { ok: false, reason: "denied" };
  } catch {
    return { ok: false, reason: "denied" };
  }
}

/** §4.11 — doble formato text/html + text/plain; degrada a copyText(plain). */
export async function copyRichText(html: string, plain: string): Promise<CopyResult> {
  if (plain === "") return { ok: false, reason: "empty" };
  const nav = typeof navigator !== "undefined" ? navigator : undefined;
  const canRich =
    typeof nav?.clipboard?.write === "function" && typeof ClipboardItem !== "undefined";
  if (canRich) {
    try {
      const item = new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      });
      await nav!.clipboard.write([item]);
      return { ok: true, method: "richClipboard" };
    } catch {
      /* degrada a texto plano */
    }
  }
  return copyText(plain);
}

/**
 * Wrapper NOMBRADO sobre flagGate (197 §6.1): resuelve la flag 194 desde el
 * array de flags del arnés. Delegado a flagEnabledFrom (semántica fail-open
 * de serie: SOLO value === false literal apaga).
 */
export function resolveCopyExportEnabled(
  flags: ReadonlyArray<{ key: string; value: unknown }> | undefined,
): boolean {
  return flagEnabledFrom(flags, COPY_EXPORT_FLAG_KEY);
}

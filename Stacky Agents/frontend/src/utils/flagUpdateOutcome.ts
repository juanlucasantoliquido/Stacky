/**
 * Clasifica el resultado de HarnessFlags.update para que ÉXITO-con-condición
 * (requiere reinicio) nunca viaje por el canal visual de error (plan 135 F5).
 */
export interface FlagUpdateResultLike {
  ok: boolean;
  error?: string | null;
  restart_required_keys?: string[] | null;
}

export interface FlagUpdateView {
  kind: "error" | "warning" | "ok";
  message: string | null;
}

export function classifyFlagUpdateOutcome(result: FlagUpdateResultLike): FlagUpdateView {
  if (!result.ok) {
    return { kind: "error", message: result.error || "Error al guardar la flag" };
  }
  const keys = result.restart_required_keys ?? [];
  if (keys.length > 0) {
    return {
      kind: "warning",
      message: `Guardado. Requiere reiniciar el backend: ${keys.join(", ")}`,
    };
  }
  return { kind: "ok", message: null };
}

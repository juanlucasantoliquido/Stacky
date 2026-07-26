import { useEffect, useState } from "react";

let _promesa: Promise<boolean> | null = null;

/**
 * Plan 212 F4 — ¿se muestra el selector de modelo/effort en el tablero?
 *
 * Optimista en `true` porque el default es ON: asumir OFF haría parpadear el
 * selector en el caso normal. Solo un `false` EXPLÍCITO lo apaga — un backend
 * viejo sin el campo, o un fetch que falla, no pueden apagar una feature que
 * está encendida por default.
 */
export function useModelPickerEnabled(): boolean {
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    let vivo = true;
    _promesa ??= fetch("/api/diag/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.model_picker_in_board_enabled !== false)
      .catch(() => true);
    void _promesa.then((v) => {
      if (vivo) setEnabled(v);
    });
    return () => {
      vivo = false;
    };
  }, []);

  return enabled;
}

export default useModelPickerEnabled;

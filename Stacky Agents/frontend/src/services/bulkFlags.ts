/**
 * bulkFlags.ts — Plan 187 F0. Lectura de STACKY_BULK_ACTIONS_ENABLED.
 *
 * WRAPPER sobre flagGate (197 §6.1): la lógica de lookup + cache + semántica
 * fail-open vive UNA sola vez en services/flagGate.ts. Este módulo conserva sus
 * exports NOMBRADOS (resolveBulkActionsEnabled + useBulkActionsEnabled) para que
 * bulkFlags.test.ts (K6) y los consumidores (F4/F5) sigan intactos.
 *
 * Semántica (heredada de flagGate): OFF ⇔ value === false literal; key ausente,
 * lista vacía, error de red o value string "false" ⇒ ON (default de la flag).
 * Staleness aceptada: se lee UNA vez por sesión; un toggle del operador aplica al
 * próximo reload del dashboard (mismo contrato que las flags restart_required).
 */
import { useEffect, useState } from "react";
import { flagEnabledFrom, getBoolFlag } from "./flagGate";

export const BULK_ACTIONS_FLAG_KEY = "STACKY_BULK_ACTIONS_ENABLED";

/** Resolver puro (K6): delega en flagEnabledFrom con la key del 187 (197 §6.1, C6). */
export function resolveBulkActionsEnabled(
  flags: ReadonlyArray<{ key: string; value: unknown }> | null | undefined,
): boolean {
  return flagEnabledFrom(flags, BULK_ACTIONS_FLAG_KEY);
}

// C2: último valor resuelto en esta sesión — mounts posteriores arrancan directo
// en él (sin flash). El primer mount arranca optimista en true (default ON).
let _last: boolean | null = null;

/** Hook de página: primer mount de la sesión arranca optimista en true (default ON)
 *  y corrige si el backend dice false (C2: flash único aceptado y documentado);
 *  mounts posteriores arrancan directo en el valor resuelto (_last) — sin flash.
 *  El fetch (1 request por sesión) se delega en flagGate.getBoolFlag. */
export function useBulkActionsEnabled(): boolean {
  const [enabled, setEnabled] = useState(() => _last ?? true);
  useEffect(() => {
    let alive = true;
    void getBoolFlag(BULK_ACTIONS_FLAG_KEY).then((v) => {
      _last = v;
      if (alive) setEnabled(v);
    });
    return () => {
      alive = false;
    };
  }, []);
  return enabled;
}

// Plan 183 F4 — Comparador de BD: lógica pura del panel del sandbox de demostración.
// Sin React ni fetch: 100% testeable con vitest node (doc §F4).

export type DemoPanelState = "cta-empty" | "cta-secondary" | "demo-active" | "demo-broken";

export interface DemoStatus {
  registered: boolean;
  files_present: boolean;
}

/** El prefijo `test-demo-` es NAMESPACE RESERVADO del sandbox (doc §3, fix C4). */
export function isDemoAlias(alias: string): boolean {
  return alias.startsWith("test-demo-");
}

/**
 * Estado del panel según el registro de ambientes + el status del backend.
 * Regla EXACTA (doc §F4, fix C6):
 *  (1) status no-null y registered !== files_present ⇒ "demo-broken";
 *  (2) algún alias `test-demo-*` ⇒ "demo-active";
 *  (3) sin ambientes ⇒ "cta-empty";
 *  (4) si no ⇒ "cta-secondary".
 */
export function demoPanelState(
  environments: { alias: string }[],
  status: DemoStatus | null
): DemoPanelState {
  if (status !== null && status.registered !== status.files_present) {
    return "demo-broken";
  }
  if (environments.some((e) => isDemoAlias(e.alias))) {
    return "demo-active";
  }
  if (environments.length === 0) {
    return "cta-empty";
  }
  return "cta-secondary";
}

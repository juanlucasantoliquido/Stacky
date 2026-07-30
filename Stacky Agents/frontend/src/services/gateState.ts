import type { FlagHealthVerdict } from "../utils/flagHealth";

/**
 * Plan 273 F7 (B-01) — tres estados. El booleano confundia "todavia no se" con
 * "esta apagado", y al montar el valor era `false` = "apagado" => rebote.
 *
 * El mecanismo sticky de `nextEnabledState` (flagHealth.ts:19-23) era CORRECTO y
 * el valor inicial lo anulaba: su docstring dice "unknown conserva el ultimo
 * estado conocido", pero `prev` al montar YA es `false`, asi que conservaba
 * exactamente el estado que dispara el rebote. Por eso B-01 no se arregla tocando
 * flagHealth.ts: se arregla introduciendo el tercer estado.
 */
export type GateState = "unknown" | "on" | "off";

/**
 * El UNICO predicado de redireccion. `unknown` NO redirige: es el fix de H-01.
 *
 * OJO — la implementacion tentadora `return state !== "on"` replica el bug
 * completo (trata `unknown` como apagado) y pasa todos los demas casos.
 * plan273GateState.test.ts la atrapa con el caso ("unknown") => false.
 */
export function shouldRedirectAway(state: GateState): boolean {
  return state === "off";
}

/**
 * Traduce el veredicto del health-check a GateState. `unknown` CONSERVA `prev`
 * (igual que nextEnabledState) pero ahora `prev` puede ser "unknown", que es la
 * diferencia con el booleano.
 */
export function gateStateFromVerdict(prev: GateState, v: FlagHealthVerdict): GateState {
  if (v === "enabled") return "on";
  if (v === "disabled") return "off";
  return prev;
}

/** True mientras el gate no resolvio: la pantalla muestra esqueleto, no rebota. */
export function isGateResolving(state: GateState): boolean {
  return state === "unknown";
}

/**
 * True solo si el gate resolvio ENCENDIDO. Existe para que los sitios que antes
 * leian el booleano en posicion de verdad no queden con un string truthy: con
 * `{devopsGate && <X/>}`, `"off"` es TRUTHY y el tab se mostraria igual, con
 * `tsc` en verde y sin un solo test rojo (C22).
 */
export function isGateOn(state: GateState): boolean {
  return state === "on";
}

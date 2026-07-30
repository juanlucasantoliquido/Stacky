import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  shouldRedirectAway,
  gateStateFromVerdict,
  isGateResolving,
  isGateOn,
  type GateState,
} from "../gateState";
import type { FlagHealthVerdict } from "../../utils/flagHealth";

/**
 * Plan 273 F7 (B-01) — el gate sin resolver no redirige, y el gate apagado avisa.
 * Test PURO: la maquina de estados + gates de texto sobre App.tsx (RTL/jsdom no
 * estan instalados, SS3.2).
 */

const APP_TSX = readFileSync(resolve(__dirname, "../../App.tsx"), "utf8");

/** Los 7 gates de tab por flag. `deepSearch` y `shellV2` NO se convierten. */
const GATES = [
  "migrador",
  "devops",
  "dbCompare",
  "costCenter",
  "planes",
  "evolution",
  "incidentInbox",
] as const;

describe("plan273 F7 — la maquina de tres estados", () => {
  it("shouldRedirectAway_tabla_completa", () => {
    // El caso "unknown" => false es EL gate de H-01.
    expect(shouldRedirectAway("unknown")).toBe(false);
    expect(shouldRedirectAway("on")).toBe(false);
    expect(shouldRedirectAway("off")).toBe(true);
  });

  it("gateStateFromVerdict_tabla_completa", () => {
    const prevs: GateState[] = ["unknown", "on", "off"];
    const verdicts: FlagHealthVerdict[] = ["enabled", "disabled", "unknown"];
    const expected: Record<string, GateState> = {
      "unknown|enabled": "on", "unknown|disabled": "off", "unknown|unknown": "unknown",
      "on|enabled": "on", "on|disabled": "off", "on|unknown": "on",
      "off|enabled": "on", "off|disabled": "off", "off|unknown": "off",
    };
    for (const p of prevs) {
      for (const v of verdicts) {
        expect(gateStateFromVerdict(p, v), `prev=${p} verdict=${v}`).toBe(expected[`${p}|${v}`]);
      }
    }
  });

  it("unknown_desde_unknown_sigue_unknown", () => {
    // La diferencia EXACTA con nextEnabledState, donde el equivalente colapsaba a
    // `false` porque `prev` al montar ya era `false`.
    expect(gateStateFromVerdict("unknown", "unknown")).toBe("unknown");
  });

  it("isGateResolving", () => {
    expect(isGateResolving("unknown")).toBe(true);
    expect(isGateResolving("on")).toBe(false);
    expect(isGateResolving("off")).toBe(false);
  });

  it("isGateOn", () => {
    expect(isGateOn("on")).toBe(true);
    expect(isGateOn("off")).toBe(false);
    expect(isGateOn("unknown")).toBe(false);
  });
});

describe("plan273 F7 — gates de texto sobre App.tsx", () => {
  it("App_no_redirige_por_gate_booleano", () => {
    // Gate de regresion: sin el, un plan futuro reintroduce el booleano.
    const offenders = APP_TSX.split("\n")
      .map((l, i) => [i + 1, l] as const)
      .filter(([, l]) => /&&\s*!(migrador|devops|dbCompare|costCenter|planes|evolution|incidentInbox)Enabled/.test(l))
      .map(([n, l]) => `App.tsx:${n}: ${l.trim()}`);
    expect(offenders, `ramas de redireccion que siguen usando el booleano:\n${offenders.join("\n")}`).toEqual([]);
  });

  it("App_declara_los_7_gates_como_GateState", () => {
    const n = (APP_TSX.match(/useState<GateState>\("unknown"\)/g) ?? []).length;
    expect(n, `hay ${n} declaraciones useState<GateState>("unknown"), se esperaban 7`).toBe(7);
  });

  it("no_se_redirige_por_seccion_sin_hidratar", () => {
    expect(
      APP_TSX.includes("if (sectionsReady)") || APP_TSX.includes("if (!sectionsReady) return"),
      "el efecto de redireccion no espera la hidratacion del store de secciones"
    ).toBe(true);
  });

  it("las_dos_cadenas_de_redireccion_estan_separadas", () => {
    // v3 C31: la guarda de sectionsReady tiene que envolver SOLO las 5 ramas de
    // seccion. Si queda arriba de la cadena unica, apaga tambien las 7 de flag y
    // la hidratacion del store bloquea los gates, que se resuelven por otra via.
    expect(APP_TSX.includes("if (sectionsReady) {"), "no existe el bloque `if (sectionsReady) {`").toBe(true);
    expect(
      /else if \(tab === "migrador"/.test(APP_TSX),
      "la primera rama de flag sigue siendo un `else if` de la cadena de secciones: " +
        "la guarda de sectionsReady la apaga tambien"
    ).toBe(false);
  });

  it("el_gate_sin_resolver_pinta_esqueleto", () => {
    const n = (APP_TSX.match(/isGateResolving\(/g) ?? []).length;
    expect(n, `hay ${n} usos de isGateResolving(, se esperaban 7`).toBe(7);
    expect(
      /import \{[^}]*\bSkeleton\b[^}]*\} from "\.\/components\/ui"/.test(APP_TSX),
      "App.tsx no importa Skeleton del barrel components/ui"
    ).toBe(true);
  });

  it("ninguna_pantalla_gateada_se_monta_en_off", () => {
    // v3 C21: el ternario del v2 era de DOS vias
    // (isGateResolving ? <Skeleton/> : <Page/>), y con eso el caso "off" renderiza
    // la pagina de una feature APAGADA, que monta y dispara sus llamadas (403).
    const dosVias = /isGateResolving\(\w+Gate\)\s*\n?\s*\?\s*<Skeleton[^>]*\/>\s*\n?\s*:\s*</g;
    const hits = [...APP_TSX.matchAll(dosVias)].map(
      (m) => `offset ${m.index}: ${m[0].replace(/\s+/g, " ").slice(0, 80)}`
    );
    expect(
      hits,
      `ternario de DOS vias: el caso "off" montaria la pagina apagada:\n${hits.join("\n")}`
    ).toEqual([]);
    const n = (APP_TSX.match(/isGateOn\(/g) ?? []).length;
    expect(n, `hay ${n} usos de isGateOn(, se esperaban al menos 7 (uno por pantalla)`).toBeGreaterThanOrEqual(7);
  });

  it("ninguna_lectura_de_gate_queda_en_posicion_booleana", () => {
    // v3 C22: `{devopsGate && (...)}` con "off" es TRUTHY => el tab se muestra
    // igual, tsc pasa en verde y ningun otro test lo mira. Es el modo de falla
    // silencioso de los 7 botones de la nav v1.
    const rx = new RegExp(`\\{\\s*(${GATES.join("|")})Gate\\s*&&`, "g");
    const offenders = APP_TSX.split("\n")
      .map((l, i) => [i + 1, l] as const)
      .filter(([, l]) => rx.test(l))
      .map(([n, l]) => `App.tsx:${n}: ${l.trim()}`);
    expect(
      offenders,
      `estos sitios leen un GateState en posicion booleana ("off" es truthy):\n${offenders.join("\n")}`
    ).toEqual([]);
  });

  it("el_gate_apagado_avisa", () => {
    expect(APP_TSX.includes("setToast("), "la redireccion sigue siendo muda").toBe(true);
    expect(
      APP_TSX.includes("se activa desde Configuración → Flags del arnés"),
      "falta el microcopy del aviso"
    ).toBe(true);
  });

  it("el_aviso_no_nombra_la_flag", () => {
    const m = APP_TSX.match(/[^\n]*se activa desde Configuración → Flags del arnés[^\n]*/);
    expect(m, "no se encontro la linea del microcopy").toBeTruthy();
    expect(m![0]).not.toMatch(/STACKY_[A-Z_]+/);
  });
});

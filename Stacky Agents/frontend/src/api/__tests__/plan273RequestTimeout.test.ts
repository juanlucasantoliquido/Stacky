import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { request, DEFAULT_TIMEOUT_MS } from "../client";
import { TimeoutError, userFacingMessage } from "../gatewayError";

/**
 * Plan 273 F6 (B-04) — deadline por defecto en request(), con override por
 * llamador para las operaciones legitimamente largas.
 *
 * Test PURO: el fetch se inyecta por `RequestOptions.fetchImpl`. Se copia el
 * PATRON de ProbeOptions (inyeccion por opcion, sin estado global,
 * flagHealth.ts:25-32), NO su firma (C16): la de probeFlagHealth es
 * `(path) => Promise<{json()}>` y no expone ok/status/statusText/text(), que es
 * justo lo que request() usa.
 *
 * NO se usan fake timers de vitest: interactuan mal con `await` sobre promesas que
 * nunca resuelven y producen tests que cuelgan la corrida.
 */

const CLIENT_SRC = readFileSync(resolve(__dirname, "../client.ts"), "utf8");
const ENDPOINTS_SRC = readFileSync(resolve(__dirname, "../endpoints.ts"), "utf8");

const jsonResponse = (body: unknown): Response =>
  ({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  }) as unknown as Response;

const never = (): Promise<Response> => new Promise<Response>(() => {});
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("plan273 F6 — deadline en request()", () => {
  it("un_fetch_que_nunca_resuelve_rechaza_por_timeout", async () => {
    // EL GATE CONTRA EL DEFECTO: hoy request() no tiene deadline y esta promesa
    // no se resolveria nunca (el test colgaria hasta el limite del runner).
    const t0 = Date.now();
    await expect(
      request("/x", { fetchImpl: never, timeoutMs: 50 })
    ).rejects.toBeInstanceOf(TimeoutError);
    expect(Date.now() - t0).toBeLessThan(500);
  });

  it("timeout_cero_no_instala_deadline", async () => {
    const raced = await Promise.race([
      request("/x", { fetchImpl: never, timeoutMs: 0 }).then(() => "resolvio").catch(() => "rechazo"),
      sleep(100).then(() => "sigue-esperando"),
    ]);
    expect(raced).toBe("sigue-esperando");
  });

  it("un_fetch_rapido_no_es_afectado", async () => {
    const out = await request<{ ok: boolean }>("/x", {
      fetchImpl: async () => jsonResponse({ ok: true }),
      timeoutMs: 50,
    });
    expect(out).toEqual({ ok: true });
  });

  it("el_abort_del_llamador_no_se_confunde_con_timeout", async () => {
    const ctl = new AbortController();
    setTimeout(() => ctl.abort(), 10);
    const err = await request("/x", {
      fetchImpl: (_i, init) =>
        new Promise<Response>((_res, rej) => {
          init?.signal?.addEventListener("abort", () =>
            rej(new DOMException("Aborted", "AbortError"))
          );
        }),
      signal: ctl.signal,
      timeoutMs: 5000,
    }).catch((e) => e);
    expect(err).not.toBeInstanceOf(TimeoutError);
    expect((err as Error).name).toBe("AbortError");
  });

  it("el_timeout_no_se_confunde_con_abort_del_llamador", async () => {
    const ctl = new AbortController(); // nunca se aborta
    const err = await request("/x", {
      fetchImpl: (_i, init) =>
        new Promise<Response>((_res, rej) => {
          init?.signal?.addEventListener("abort", () =>
            rej(new DOMException("Aborted", "AbortError"))
          );
        }),
      signal: ctl.signal,
      timeoutMs: 20,
    }).catch((e) => e);
    expect(err).toBeInstanceOf(TimeoutError);
  });

  it("ufm_de_un_timeout_es_accionable", () => {
    const r = userFacingMessage(new TimeoutError("/api/x", 20000));
    expect(r.isTimeout).toBe(true);
    expect(r.title).toContain("tardó");
    expect(r.title).not.toMatch(/^\d{3}/);
  });

  it("el_default_es_20000", () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(20000);
  });

  it("se_limpia_el_timer_en_el_camino_feliz", async () => {
    // Sin clearTimeout, cada request deja un timer vivo hasta 20s; con navegacion
    // intensa se acumulan.
    const realSet = globalThis.setTimeout;
    const realClear = globalThis.clearTimeout;
    let sets = 0;
    let clears = 0;
    try {
      (globalThis as any).setTimeout = ((fn: any, ms?: number) => {
        sets++;
        return realSet(fn, ms);
      }) as typeof setTimeout;
      (globalThis as any).clearTimeout = ((h: any) => {
        clears++;
        return realClear(h);
      }) as typeof clearTimeout;
      await request("/x", { fetchImpl: async () => jsonResponse({ ok: true }), timeoutMs: 5000 });
    } finally {
      (globalThis as any).setTimeout = realSet;
      (globalThis as any).clearTimeout = realClear;
    }
    expect(sets).toBe(1);
    expect(clears).toBe(1);
  });
});

// ── Gates estructurales sobre el fuente ───────────────────────────────────────

/** Los 12 endpoints largos que van con `timeoutMs: 0` (v3, C23: 10 + los 2 de postWithHeaders). */
const LONG_ENDPOINTS: Array<[string, string]> = [
  ["/api/tickets/sync", "sincronizacion completa contra ADO/GitLab"],
  ["/api/agents/run", "ejecucion de agente (DOS sitios)"],
  ["/api/packs/start", "arranque de pack multi-paso"],
  ["/publish-to-ado", "publicacion en el sistema real del operador"],
  ["/api/config/import", "importacion de bundle (DOS sitios)"],
  ["/api/drift/run", "barrido de drift"],
  ["/api/glossary/scan", "escaneo de glosario"],
  ["/api/qa-uat/run", "corrida QA/UAT"],
  ["/api/qa-browser/runs", "corrida de navegador"],
  ["/api/diag/backup/run", "backup"],
  ["/finish-work", "cancela ejecucion + publica en ADO + transiciona el estado (C23)"],
  ["/create-child-task", "crea una Task en ADO (C23)"],
];

describe("plan273 F6 — gates estructurales", () => {
  it("los_verbos_aceptan_opts", () => {
    // v2 C2 + v3 C23: son SEIS los verbos que enrutan por request().
    const missing = (
      ["post", "put", "patch", "delete", "postWithHeaders", "postAbortable"] as const
    ).filter((v) => {
      const m = CLIENT_SRC.match(new RegExp(`${v}:\\s*<T,?>\\([^)]*\\)`, "s"));
      return !m || !m[0].includes("opts?: RequestOptions");
    });
    expect(
      missing,
      `estos verbos no declaran \`opts?: RequestOptions\`, asi que su deadline es ` +
        `INESCAPABLE: ${missing.join(", ")}`
    ).toEqual([]);
  });

  it("los_12_endpoints_largos_declaran_timeout_cero", () => {
    const missing: string[] = [];
    for (const [route, why] of LONG_ENDPOINTS) {
      // Ventana alrededor de cada mencion de la ruta; alguna tiene que traer timeoutMs: 0.
      const idxs: number[] = [];
      let i = ENDPOINTS_SRC.indexOf(route);
      while (i >= 0) {
        idxs.push(i);
        i = ENDPOINTS_SRC.indexOf(route, i + 1);
      }
      const ok = idxs.some((at) =>
        ENDPOINTS_SRC.slice(at, at + 420).includes("timeoutMs: 0")
      );
      if (!ok) missing.push(`${route} — ${why}`);
    }
    expect(
      missing,
      `estas operaciones largas siguen con el deadline de 20s y sin escape:\n` +
        missing.join("\n")
    ).toEqual([]);
  });

  it("el_conteo_de_timeout_cero_no_baja", () => {
    const n = (ENDPOINTS_SRC.match(/timeoutMs:\s*0/g) ?? []).length;
    // 12 rutas, y /api/agents/run y /api/config/import aparecen dos veces cada una
    // => 14 sitios. Ratchet: si alguien borra un timeoutMs: 0, se pone rojo.
    expect(n, `solo ${n} sitios con timeoutMs: 0 en endpoints.ts`).toBeGreaterThanOrEqual(14);
  });

  it("ningun_verbo_enruta_por_request_sin_canal_de_deadline", () => {
    // [ADICION ARQUITECTO v3] C2 y C23 son EL MISMO defecto encontrado dos veces:
    // un verbo que enruta por request(), hereda el deadline y no tiene por donde
    // escaparlo. El fix duradero no es "acordarse de los 6": es congelar la
    // invariante para el 7o verbo que alguien agregue.
    const block = CLIENT_SRC.match(/export const api = \{([\s\S]*?)\n\};/);
    expect(block, "no se encontro el bloque `export const api = {`").toBeTruthy();
    const body = block![1];

    // Cada miembro de primer nivel: `nombre: <T,>(...) => ...`
    const members = [...body.matchAll(/^\s{2}(\w+):\s*<T,?>/gm)].map((m) => m[1]);
    expect(
      members.length,
      `se detectaron ${members.length} verbos en \`api\` (${members.join(", ")}): ` +
        `el parser esta roto y este caso pasaria EN FALSO`
    ).toBe(7);

    const sinCanal: string[] = [];
    for (const v of members) {
      const seg = body.slice(body.indexOf(`  ${v}:`));
      const decl = seg.slice(0, seg.indexOf("=>") + 2);
      const impl = seg.slice(0, 400);
      if (!impl.includes("request<T>(")) continue; // no enruta por request(): no aplica
      if (!/opts\?: RequestOptions|init\?: RequestOptions/.test(decl)) sinCanal.push(v);
    }
    expect(
      sinCanal,
      `estos verbos enrutan por request() y NO tienen canal de deadline: ` +
        `${sinCanal.join(", ")}. Un verbo sin override es un timeout inescapable ` +
        `esperando su endpoint largo (C23: era postWithHeaders, el verbo de finish-work).`
    ).toEqual([]);
  });
});

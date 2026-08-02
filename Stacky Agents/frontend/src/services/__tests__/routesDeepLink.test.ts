// Plan 165 F3 — Tests de deep-links de subestado (lógica pura de parseo).
// Los componentes (que el drawer/subtab realmente abran) se verifican por smoke.
import { describe, it, expect } from "vitest";
import { parseRoute } from "../routes";
import { isValidSubTab } from "../settingsSubTabs";

describe("deep-links de subestado (Plan 165 F3)", () => {
  it("deeplink_settings_subtab", () => {
    expect(parseRoute("/settings/appearance", "")).toMatchObject({
      tab: "settings", subtab: "appearance",
    });
  });

  it("deeplink_settings_subtab_invalido", () => {
    // routes.ts NO valida el subtab; la validación vive en isValidSubTab.
    expect(parseRoute("/settings/xyz", "").subtab).toBe("xyz");
    expect(isValidSubTab("appearance")).toBe(true);
    expect(isValidSubTab("xyz")).toBe(false);
    expect(isValidSubTab(null)).toBe(false);
    expect(isValidSubTab(undefined)).toBe(false);
  });

  it("deeplink_history_exec", () => {
    expect(parseRoute("/history", "?exec=123")).toMatchObject({
      tab: "history", exec: 123,
    });
  });

  it("deeplink_slack_root_exec", () => {
    // el link de Slack (/?exec=) ahora normaliza a history y abre el drawer.
    expect(parseRoute("/", "?exec=123")).toMatchObject({
      tab: "history", exec: 123,
    });
  });

  it("deeplink_alias_execution", () => {
    expect(parseRoute("/history", "?execution=456").exec).toBe(456);
  });

  it("deeplink_preserva_flag", () => {
    // el receptor ?flag= (Settings) conserva su dato pese al subtab por path.
    expect(parseRoute("/settings/harness", "?flag=STACKY_X")).toMatchObject({
      tab: "settings", subtab: "harness", query: { flag: "STACKY_X" },
    });
  });

  // ── Plan 287 F5 — la ficha del ticket ─────────────────────────────────────

  it("deeplink_ticket_en_raiz", () => {
    // El caso soportado de punta a punta: ?ticket= EN LA RAÍZ, que ya es el
    // tablero (TAB_PATHS.tickets === "/"), donde la ficha se monta.
    expect(parseRoute("/", "?ticket=88")).toMatchObject({
      tab: "tickets", ticket: 88,
    });
  });

  it("deeplink_ticket_convive_con_exec", () => {
    // v2/C14 — LÍMITE HONESTO: esto verifica la SUPERVIVENCIA del parámetro, NO
    // la apertura de la ficha. `normalizeInitial` fuerza tab:"history" cuando hay
    // exec, y la ficha vive en el tablero: con este URL TicketBoard ni se monta.
    // El caso que sí abre la ficha es ?ticket= en la raíz (test de arriba).
    const r = parseRoute("/", "?exec=5&ticket=9");
    expect(r.tab).toBe("history");     // manda la regla vigente de exec
    expect(r.ticket).toBe(9);          // pero el parámetro NO se pierde…
    expect(r.query.ticket).toBeUndefined();  // …ni degrada a query verbatim
  });
});

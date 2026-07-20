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
});

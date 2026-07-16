import { describe, it, expect } from "vitest";
import { resolveVisibleIntegrations, shouldRenderBanner } from "../integrationHealth.logic";
import type { IntegrationHealthItem, IntegrationsStatusResponse } from "../../api/endpoints";

const ITEM: IntegrationHealthItem = {
  key: "ado_sync::RSPACIFICO",
  integration: "ado_sync",
  project: "RSPACIFICO",
  reason: "ado_pat_expired",
  title: "PAT de Azure DevOps expirado",
  action: "Renová el PAT en la Caja Fuerte",
  vault: true,
  message: "El PAT de Azure DevOps expiró.",
  retry_after: "2026-07-16T12:00:00Z",
  seconds_until_retry: 900,
};

describe("integrationHealth.logic (Plan 148 F6)", () => {
  describe("resolveVisibleIntegrations", () => {
    it("devuelve [] cuando la respuesta es null/undefined", () => {
      expect(resolveVisibleIntegrations(null)).toEqual([]);
      expect(resolveVisibleIntegrations(undefined)).toEqual([]);
    });

    it("devuelve [] cuando enabled:false (flag master OFF)", () => {
      const data: IntegrationsStatusResponse = { enabled: false, integrations: [ITEM] };
      expect(resolveVisibleIntegrations(data)).toEqual([]);
    });

    it("devuelve la lista de integraciones cuando enabled:true", () => {
      const data: IntegrationsStatusResponse = { enabled: true, integrations: [ITEM] };
      expect(resolveVisibleIntegrations(data)).toEqual([ITEM]);
    });

    it("devuelve [] cuando enabled:true pero sin integraciones caídas", () => {
      const data: IntegrationsStatusResponse = { enabled: true, integrations: [] };
      expect(resolveVisibleIntegrations(data)).toEqual([]);
    });
  });

  describe("shouldRenderBanner", () => {
    it("false con lista vacía (cero ruido cuando todo está sano)", () => {
      expect(shouldRenderBanner([])).toBe(false);
    });

    it("true con al menos una integración caída", () => {
      expect(shouldRenderBanner([ITEM])).toBe(true);
    });
  });
});

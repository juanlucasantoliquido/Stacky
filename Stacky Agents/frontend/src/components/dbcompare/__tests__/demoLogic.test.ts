import { describe, it, expect } from "vitest";
import { demoPanelState, isDemoAlias } from "../demoLogic";

describe("Plan 183 F4 — demoLogic (pure)", () => {
  describe("isDemoAlias", () => {
    it("reconoce el prefijo reservado", () => {
      expect(isDemoAlias("test-demo-dev")).toBe(true);
      expect(isDemoAlias("test-demo-test")).toBe(true);
    });
    it("rechaza aliases ajenos", () => {
      expect(isDemoAlias("prod-x")).toBe(false);
      expect(isDemoAlias("test-otro")).toBe(false);
    });
  });

  describe("demoPanelState", () => {
    it("sin ambientes y sin status ⇒ cta-empty", () => {
      expect(demoPanelState([], null)).toBe("cta-empty");
    });

    it("con ambientes ajenos y sin status ⇒ cta-secondary", () => {
      expect(demoPanelState([{ alias: "prod-x" }], null)).toBe("cta-secondary");
    });

    it("con alias demo y status sano ⇒ demo-active", () => {
      const state = demoPanelState(
        [{ alias: "test-demo-dev" }, { alias: "test-demo-test" }],
        { registered: true, files_present: true }
      );
      expect(state).toBe("demo-active");
    });

    it("registrado sin archivos ⇒ demo-broken (fix C6)", () => {
      expect(
        demoPanelState([{ alias: "test-demo-dev" }], { registered: true, files_present: false })
      ).toBe("demo-broken");
    });

    it("archivos sin registro ⇒ demo-broken (fix C6, otra dirección)", () => {
      expect(
        demoPanelState([], { registered: false, files_present: true })
      ).toBe("demo-broken");
    });

    it("demo-broken tiene prioridad sobre demo-active", () => {
      // registrado + con alias demo pero archivos ausentes ⇒ roto, no activo.
      expect(
        demoPanelState([{ alias: "test-demo-dev" }], { registered: true, files_present: false })
      ).toBe("demo-broken");
    });
  });
});

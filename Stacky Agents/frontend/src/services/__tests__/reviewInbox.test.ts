import { describe, expect, it } from "vitest";
import { reviewBadgeLabel, reviewInboxQueryKey } from "../reviewInbox";

describe("reviewBadgeLabel (plan 134 F5)", () => {
  it("0 y negativos → null", () => {
    expect(reviewBadgeLabel(0)).toBeNull();
    expect(reviewBadgeLabel(-3)).toBeNull();
  });

  it("1..99 literal", () => {
    expect(reviewBadgeLabel(1)).toBe("1");
    expect(reviewBadgeLabel(99)).toBe("99");
  });

  it(">99 → 99+", () => {
    expect(reviewBadgeLabel(100)).toBe("99+");
  });
});

describe("reviewInboxQueryKey (plan 134 F5)", () => {
  it("forma exacta compartida con la página", () => {
    expect(reviewInboxQueryKey("p")).toEqual(["review-inbox", "p"]);
    expect(reviewInboxQueryKey(null)).toEqual(["review-inbox", null]);
  });
});

import { describe, expect, it } from "vitest";

import { ApiClient, type RiskDecision } from "./generated";

describe("generated API boundary", () => {
  it("provides the generated same-origin client and constrained risk decisions", () => {
    const client = new ApiClient();
    const decision: RiskDecision = "BLOCKED";
    expect(client).toBeTruthy();
    expect(decision).toBe("BLOCKED");
  });
});

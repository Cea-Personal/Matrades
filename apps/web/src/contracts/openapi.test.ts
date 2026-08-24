import { describe, expect, it } from "vitest";
import { CONTRACT_VERSION, type RuntimeType } from "../../../../packages/contracts/generated/openapi";

describe("generated contract", () => {
  it("pins the V1 contract and supported runtime names", () => {
    const runtimes: RuntimeType[] = ["CODEX_APP_SERVER", "LITELLM_GATEWAY"];
    expect(CONTRACT_VERSION).toBe("matrades.openapi.v1");
    expect(runtimes).toHaveLength(2);
  });
});

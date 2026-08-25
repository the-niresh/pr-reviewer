import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";

import { verifyGitHubSignature } from "./verifySignature";

describe("verifyGitHubSignature", () => {
  const body = Buffer.from(JSON.stringify({ action: "opened" }));
  const secret = "test-webhook-secret";

  it("accepts a valid sha256 signature", () => {
    const signature = `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;

    expect(verifyGitHubSignature(body, signature, secret)).toBe(true);
  });

  it("rejects an invalid signature", () => {
    expect(verifyGitHubSignature(body, "sha256=bad", secret)).toBe(false);
  });

  it("rejects a signature with an unsupported prefix", () => {
    expect(verifyGitHubSignature(body, "sha1=deadbeef", secret)).toBe(false);
  });

  it("rejects verification without a configured secret", () => {
    const signature = `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;

    expect(verifyGitHubSignature(body, signature, "")).toBe(false);
  });
});

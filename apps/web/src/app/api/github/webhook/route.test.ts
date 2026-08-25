import { createHmac } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

const { enqueueReviewJob } = vi.hoisted(() => ({ enqueueReviewJob: vi.fn() }));

vi.mock("@pr-reviewer/core/src/jobs/enqueueReviewJob", () => ({
  enqueueReviewJob,
}));

import { MAX_WEBHOOK_BODY_BYTES, POST } from "./route";

describe("POST /api/github/webhook", () => {
  const secret = "test-webhook-secret";

  afterEach(() => {
    enqueueReviewJob.mockReset();
    delete process.env.GITHUB_WEBHOOK_SECRET;
  });

  it("verifies and enqueues a pull request delivery", async () => {
    enqueueReviewJob.mockResolvedValue("enqueued");
    const response = await POST(signedRequest(JSON.stringify({ action: "opened" })));

    expect(response.status).toBe(202);
    await expect(response.json()).resolves.toEqual({ result: "enqueued" });
    expect(enqueueReviewJob).toHaveBeenCalledWith(
      "delivery-1",
      "pull_request",
      { action: "opened" },
    );
  });

  it("returns 200 for a duplicate delivery", async () => {
    enqueueReviewJob.mockResolvedValue("duplicate");

    const response = await POST(signedRequest(JSON.stringify({ action: "opened" })));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ result: "duplicate" });
  });

  it("returns 200 for a verified non-pull-request event", async () => {
    enqueueReviewJob.mockResolvedValue("ignored");

    const response = await POST(signedRequest(JSON.stringify({ ref: "main" }), "push"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ result: "ignored" });
  });

  it("rejects requests without the required delivery headers", async () => {
    const response = await POST(new Request("http://localhost/api/github/webhook", { method: "POST" }));

    expect(response.status).toBe(400);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  it("rejects an invalid signature before enqueueing", async () => {
    const response = await POST(
      new Request("http://localhost/api/github/webhook", {
        body: JSON.stringify({ action: "opened" }),
        headers: {
          "x-github-delivery": "delivery-1",
          "x-github-event": "pull_request",
          "x-hub-signature-256": "sha256=invalid",
        },
        method: "POST",
      }),
    );

    expect(response.status).toBe(401);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  it("rejects malformed JSON with an invalid signature before parsing it", async () => {
    const response = await POST(
      new Request("http://localhost/api/github/webhook", {
        body: "{invalid",
        headers: {
          "x-github-delivery": "delivery-1",
          "x-github-event": "pull_request",
          "x-hub-signature-256": "sha256=invalid",
        },
        method: "POST",
      }),
    );

    expect(response.status).toBe(401);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  it("rejects an absent signature", async () => {
    const response = await POST(
      new Request("http://localhost/api/github/webhook", {
        body: JSON.stringify({ action: "opened" }),
        headers: {
          "x-github-delivery": "delivery-1",
          "x-github-event": "pull_request",
        },
        method: "POST",
      }),
    );

    expect(response.status).toBe(401);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  it("rejects malformed JSON after signature verification", async () => {
    const response = await POST(signedRequest("{invalid"));

    expect(response.status).toBe(400);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  it("rejects a body over the configured limit before verification or enqueueing", async () => {
    const response = await POST(signedRequest("x".repeat(MAX_WEBHOOK_BODY_BYTES + 1)));

    expect(response.status).toBe(413);
    expect(enqueueReviewJob).not.toHaveBeenCalled();
  });

  function signedRequest(body: string, eventName = "pull_request"): Request {
    process.env.GITHUB_WEBHOOK_SECRET = secret;
    const signature = createHmac("sha256", secret).update(body).digest("hex");

    return new Request("http://localhost/api/github/webhook", {
      body,
      headers: {
        "x-github-delivery": "delivery-1",
        "x-github-event": eventName,
        "x-hub-signature-256": `sha256=${signature}`,
      },
      method: "POST",
    });
  }
});

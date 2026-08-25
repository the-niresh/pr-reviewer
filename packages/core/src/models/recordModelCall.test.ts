import { afterEach, describe, expect, it, vi } from "vitest";

const { connect } = vi.hoisted(() => ({ connect: vi.fn() }));

vi.mock("../db/client", () => ({
  db: { connect },
}));

import { recordModelCall } from "./recordModelCall";

describe("recordModelCall", () => {
  afterEach(() => {
    connect.mockReset();
  });

  it("records a cost row and a linked event in one transaction", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null, rows: [] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ id: "model-call-1" }] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [] })
      .mockResolvedValueOnce({ rowCount: null, rows: [] });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await recordModelCall({
      reviewJobId: "job-1",
      provider: "openai",
      model: "gpt-5-mini",
      promptVersion: "00000000-0000-0000-0000-000000000001",
      inputTokens: 123,
      outputTokens: 45,
      costUsd: "0.001234",
      latencyMs: 678,
      metadata: { requestId: "req-1" },
    });

    expect(query).toHaveBeenNthCalledWith(1, "begin");
    expect(query).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("insert into model_calls"),
      [
        "job-1",
        "00000000-0000-0000-0000-000000000001",
        "openai",
        "gpt-5-mini",
        123,
        45,
        "0.001234",
        JSON.stringify({ requestId: "req-1" }),
        JSON.stringify({ latencyMs: 678 }),
      ],
    );
    expect(query).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("insert into agent_events"),
      [
        "job-1",
        "model_call.recorded",
        JSON.stringify({
          modelCallId: "model-call-1",
          provider: "openai",
          model: "gpt-5-mini",
          promptVersion: "00000000-0000-0000-0000-000000000001",
          inputTokens: 123,
          outputTokens: 45,
          costUsd: "0.001234",
          latencyMs: 678,
        }),
      ],
    );
    expect(query).toHaveBeenNthCalledWith(4, "commit");
    expect(release).toHaveBeenCalledOnce();
  });

  it("rolls back when the event cannot be written", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rowCount: null, rows: [] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ id: "model-call-1" }] })
      .mockRejectedValueOnce(new Error("event insert failed"))
      .mockResolvedValueOnce({ rowCount: null, rows: [] });
    const release = vi.fn();
    connect.mockResolvedValue({ query, release });

    await expect(
      recordModelCall({
        reviewJobId: "job-1",
        provider: "anthropic",
        model: "claude-sonnet",
        promptVersion: "00000000-0000-0000-0000-000000000001",
        inputTokens: 1,
        outputTokens: 2,
        costUsd: "0",
        latencyMs: 3,
        metadata: {},
      }),
    ).rejects.toThrow("event insert failed");

    expect(query).toHaveBeenNthCalledWith(4, "rollback");
    expect(release).toHaveBeenCalledOnce();
  });
});

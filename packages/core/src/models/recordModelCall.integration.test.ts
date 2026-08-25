import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";

import { db } from "../db/client";
import { migrate } from "../db/migrate";
import { listEventsForJob } from "../events/listEventsForJob";
import { recordModelCall } from "./recordModelCall";

describe("model call ledger database integration", () => {
  beforeAll(async () => {
    await migrate();
  });

  afterAll(async () => {
    await db.end();
  });

  it("persists the cost, prompt version, latency, and linked event", async () => {
    const reviewJobId = await createReviewJob();
    const promptVersionId = randomUUID();
    await db.query(
      "insert into prompt_versions (id, name, version, content) values ($1, $2, $3, $4)",
      [promptVersionId, "review", `test-${randomUUID()}`, "test prompt"],
    );

    await recordModelCall({
      reviewJobId,
      provider: "openai",
      model: "gpt-5-mini",
      promptVersion: promptVersionId,
      inputTokens: 123,
      outputTokens: 45,
      costUsd: "0.000000000001",
      latencyMs: 678,
      metadata: { requestId: "req-1" },
    });

    const modelCalls = await db.query<{
      id: string;
      prompt_version_id: string;
      provider: string;
      model_name: string;
      input_tokens: number;
      output_tokens: number;
      cost_usd: string;
      latency_ms: number;
      request_metadata: { requestId: string };
      response_metadata: Record<string, never>;
    }>(
      `select id, prompt_version_id, provider, model_name, input_tokens, output_tokens,
              cost_usd::text, latency_ms, request_metadata, response_metadata
       from model_calls
       where review_job_id = $1`,
      [reviewJobId],
    );
    const events = await listEventsForJob(reviewJobId);

    expect(modelCalls.rows).toEqual([
      expect.objectContaining({
        prompt_version_id: promptVersionId,
        provider: "openai",
        model_name: "gpt-5-mini",
        input_tokens: 123,
        output_tokens: 45,
        cost_usd: "0.000000000001",
        latency_ms: 678,
        request_metadata: { requestId: "req-1" },
        response_metadata: {},
      }),
    ]);
    expect(events).toHaveLength(1);
    expect(events[0].payload).toMatchObject({
      modelCallId: modelCalls.rows[0].id,
      costUsd: "0.000000000001",
      latencyMs: 678,
    });
  });
});

async function createReviewJob(): Promise<string> {
  const deliveryId = `model-delivery-${randomUUID()}`;
  await db.query("insert into github_deliveries (id, event_name) values ($1, 'pull_request')", [deliveryId]);
  const result = await db.query<{ id: string }>(
    "insert into review_jobs (delivery_id, status) values ($1, 'succeeded') returning id",
    [deliveryId],
  );
  return result.rows[0].id;
}

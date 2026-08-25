import { db } from "../db/client";
import { serializeJsonObject, type JsonObject } from "../events/recordEvent";

export type ModelProvider = "openai" | "anthropic";

export type ModelCallInput = {
  reviewJobId: string;
  provider: ModelProvider;
  model: string;
  promptVersion: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: string;
  latencyMs: number;
  metadata: JsonObject;
};

type InsertedModelCall = {
  id: string;
};

export async function recordModelCall(input: ModelCallInput): Promise<void> {
  validateModelCallInput(input);
  const client = await db.connect();

  try {
    await client.query("begin");
    const result = await client.query<InsertedModelCall>(
      `insert into model_calls (
         review_job_id,
         prompt_version_id,
         provider,
         model_name,
         input_tokens,
         output_tokens,
         cost_usd,
         request_metadata,
         response_metadata
       )
       values ($1, $2, $3, $4, $5, $6, $7::numeric, $8::jsonb, $9::jsonb)
       returning id`,
      [
        input.reviewJobId,
        input.promptVersion,
        input.provider,
        input.model,
        input.inputTokens,
        input.outputTokens,
        input.costUsd,
        serializeJsonObject(input.metadata),
        serializeJsonObject({ latencyMs: input.latencyMs }),
      ],
    );

    const modelCall = result.rows[0];
    if (modelCall === undefined) {
      throw new Error("Model call insert did not return an id");
    }

    await client.query(
      `insert into agent_events (review_job_id, event_type, payload)
       values ($1, $2, $3::jsonb)`,
      [
        input.reviewJobId,
        "model_call.recorded",
        serializeJsonObject({
          modelCallId: modelCall.id,
          provider: input.provider,
          model: input.model,
          promptVersion: input.promptVersion,
          inputTokens: input.inputTokens,
          outputTokens: input.outputTokens,
          costUsd: input.costUsd,
          latencyMs: input.latencyMs,
        }),
      ],
    );
    await client.query("commit");
  } catch (error) {
    await client.query("rollback");
    throw error;
  } finally {
    client.release();
  }
}

function validateModelCallInput(input: ModelCallInput): void {
  if (!Number.isSafeInteger(input.inputTokens) || input.inputTokens < 0) {
    throw new TypeError("inputTokens must be a non-negative safe integer");
  }
  if (!Number.isSafeInteger(input.outputTokens) || input.outputTokens < 0) {
    throw new TypeError("outputTokens must be a non-negative safe integer");
  }
  if (!Number.isSafeInteger(input.latencyMs) || input.latencyMs < 0) {
    throw new TypeError("latencyMs must be a non-negative safe integer");
  }
  if (!/^\d+(?:\.\d+)?$/.test(input.costUsd)) {
    throw new TypeError("costUsd must be a non-negative decimal string");
  }
}

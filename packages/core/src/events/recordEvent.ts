import { db } from "../db/client";

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type KnownAgentEventType =
  | "webhook.accepted"
  | "model_call.recorded"
  | "review_job_failed"
  | "review_job_retry_scheduled";

export type AgentEventType = KnownAgentEventType | (string & {});

export type RecordEventInput = {
  reviewJobId: string;
  eventType: AgentEventType;
  payload: JsonObject;
};

export type AgentEvent = {
  id: string;
  sequence: string;
  reviewJobId: string | null;
  eventType: AgentEventType;
  payload: JsonObject;
  createdAt: Date;
};

export async function recordEvent(input: RecordEventInput): Promise<void> {
  await db.query(
    `insert into agent_events (review_job_id, event_type, payload)
     values ($1, $2, $3::jsonb)`,
    [input.reviewJobId, input.eventType, serializeJsonObject(input.payload)],
  );
}

export function serializeJsonObject(value: JsonObject): string {
  assertJsonValue(value, "$", new Set<object>());
  return JSON.stringify(value);
}

function assertJsonValue(value: unknown, path: string, ancestors: Set<object>): asserts value is JsonValue {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return;
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError(`Expected a finite JSON number at ${path}`);
    }
    return;
  }

  if (Array.isArray(value)) {
    assertAcyclic(value, path, ancestors);
    for (const [index, item] of value.entries()) {
      assertJsonValue(item, `${path}[${index}]`, ancestors);
    }
    ancestors.delete(value);
    return;
  }

  if (typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError(`Expected a JSON object at ${path}`);
    }

    assertAcyclic(value, path, ancestors);
    for (const [key, item] of Object.entries(value)) {
      assertJsonValue(item, `${path}.${key}`, ancestors);
    }
    ancestors.delete(value);
    return;
  }

  throw new TypeError(`Expected a JSON value at ${path}`);
}

function assertAcyclic(value: object, path: string, ancestors: Set<object>): void {
  if (ancestors.has(value)) {
    throw new TypeError(`Expected an acyclic JSON value at ${path}`);
  }
  ancestors.add(value);
}

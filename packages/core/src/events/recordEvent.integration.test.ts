import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";

import { db } from "../db/client";
import { migrate } from "../db/migrate";
import { listEventsForJob } from "./listEventsForJob";
import { recordEvent } from "./recordEvent";

describe("event spine database integration", () => {
  beforeAll(async () => {
    await migrate();
  });

  afterAll(async () => {
    await db.end();
  });

  it("persists append-only events for a review job", async () => {
    const reviewJobId = await createReviewJob();

    await recordEvent({
      reviewJobId,
      eventType: "webhook.accepted",
      payload: { deliveryId: "event-delivery" },
    });

    const events = await listEventsForJob(reviewJobId);

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      reviewJobId,
      eventType: "webhook.accepted",
      payload: { deliveryId: "event-delivery" },
    });
  });
});

async function createReviewJob(): Promise<string> {
  const deliveryId = `event-delivery-${randomUUID()}`;
  await db.query("insert into github_deliveries (id, event_name) values ($1, 'pull_request')", [deliveryId]);
  const result = await db.query<{ id: string }>(
    "insert into review_jobs (delivery_id, status) values ($1, 'pending') returning id",
    [deliveryId],
  );
  return result.rows[0].id;
}

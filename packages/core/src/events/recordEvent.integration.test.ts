import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";

import { db } from "../db/client";
import { migrate } from "../db/migrate";
import { listEventsForJob } from "./listEventsForJob";

describe("event spine database integration", () => {
  beforeAll(async () => {
    await migrate();
  });

  afterAll(async () => {
    await db.end();
  });

  it("lists events in append sequence when timestamps are out of order", async () => {
    const reviewJobId = await createReviewJob();

    await db.query(
      `insert into agent_events (review_job_id, event_type, payload, created_at)
       values
         ($1, 'webhook.accepted', '{"deliveryId":"first"}', '2026-08-26T12:00:00.000Z'),
         ($1, 'webhook.accepted', '{"deliveryId":"second"}', '2026-08-26T11:00:00.000Z')`,
      [reviewJobId],
    );

    const events = await listEventsForJob(reviewJobId);

    expect(events.map((event) => event.payload)).toEqual([
      { deliveryId: "first" },
      { deliveryId: "second" },
    ]);
    expect(Number(events[0].sequence)).toBeLessThan(Number(events[1].sequence));
  });
});

async function createReviewJob(): Promise<string> {
  const deliveryId = `event-delivery-${randomUUID()}`;
  await db.query("insert into github_deliveries (id, event_name) values ($1, 'pull_request')", [deliveryId]);
  const result = await db.query<{ id: string }>(
    "insert into review_jobs (delivery_id, status) values ($1, 'succeeded') returning id",
    [deliveryId],
  );
  return result.rows[0].id;
}

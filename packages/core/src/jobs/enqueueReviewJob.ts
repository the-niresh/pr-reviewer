import { db } from "../db/client";

export type EnqueueReviewJobResult = "enqueued" | "duplicate" | "ignored";

export async function enqueueReviewJob(
  deliveryId: string,
  eventName: string,
  _payload: unknown,
): Promise<EnqueueReviewJobResult> {
  if (eventName !== "pull_request") {
    return "ignored";
  }

  const client = await db.connect();

  try {
    await client.query("begin");

    const delivery = await client.query<{ id: string }>(
      `insert into github_deliveries (id, event_name)
       values ($1, $2)
       on conflict (id) do nothing
       returning id`,
      [deliveryId, eventName],
    );

    if (delivery.rowCount === 0) {
      await client.query("rollback");
      return "duplicate";
    }

    await client.query(
      `insert into review_jobs (delivery_id, status)
       values ($1, 'pending')`,
      [deliveryId],
    );

    await client.query("commit");
    return "enqueued";
  } catch (error) {
    await client.query("rollback");
    throw error;
  } finally {
    client.release();
  }
}

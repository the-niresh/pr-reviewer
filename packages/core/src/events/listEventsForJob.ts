import { db } from "../db/client";
import type { AgentEvent } from "./recordEvent";

export async function listEventsForJob(reviewJobId: string): Promise<AgentEvent[]> {
  const result = await db.query<AgentEvent>(
    `select
       id,
       review_job_id as "reviewJobId",
       event_type as "eventType",
       payload,
       created_at as "createdAt"
     from agent_events
     where review_job_id = $1
     order by created_at asc, id asc`,
    [reviewJobId],
  );

  return result.rows;
}

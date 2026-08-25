import { db } from "../db/client";

export async function completeReviewJob(jobId: string, workerId: string): Promise<void> {
  const result = await db.query<{ id: string }>(
    `update review_jobs
     set status = 'succeeded', locked_by = null, locked_until = null, updated_at = now()
     where id = $1 and status = 'running' and locked_by = $2
     returning id`,
    [jobId, workerId],
  );

  if (result.rowCount !== 1) {
    throw new Error(`Review job is not owned by worker: ${jobId}`);
  }
}
